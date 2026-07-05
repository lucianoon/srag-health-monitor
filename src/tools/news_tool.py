"""
Ferramenta de busca de notícias reais sobre SRAG e saúde pública.

As notícias são obtidas de feeds RSS de fontes oficiais/reconhecidas em
vigilância epidemiológica no Brasil (Agência Fiocruz de Notícias e Agência
Brasil/EBC — editoria de Saúde). Os itens são ordenados por relevância ao tema
de SRAG/vírus respiratórios e por data. Em caso de falha de rede ou parsing, a
ferramenta degrada para uma lista vazia — nunca fabrica notícias nem números.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET
import logging
import re

import requests
from bs4 import BeautifulSoup
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from config import DEFAULT_NEWS_FEEDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Termos que tornam uma notícia relevante para um relatório de SRAG.
RELEVANCE_TERMS = (
    "srag",
    "síndrome respiratória",
    "sindrome respiratoria",
    "infogripe",
    "gripe",
    "influenza",
    "covid",
    "sars-cov",
    "vsr",
    "vírus sincicial",
    "respiratór",
    "vacina",
    "imuniza",
    "sivep",
    "vigilância epidemiológica",
    "surto",
    "internaç",
    "uti",
)

# Títulos de itens de navegação presentes no feed da Fiocruz.
_JUNK_TITLE_PREFIXES = ("nav.", "navegação", "menu")

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SRAGHealthMonitor/1.0; "
        "+https://github.com/lucianoon/srag-health-monitor)"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


def _element_text(item: ET.Element, tag: str) -> str:
    """Retorna o texto de um filho (ignorando namespace) ou string vazia."""
    child = item.find(f"{{*}}{tag}")
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _clean_summary(raw_html: str, max_length: int = 320) -> str:
    """Remove marcação HTML e normaliza o resumo da notícia."""
    if not raw_html:
        return ""
    text = BeautifulSoup(raw_html, "html.parser").get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        text = text[:max_length].rstrip() + "…"
    return text


def _normalize_date(raw_date: str) -> str:
    """Converte datas RSS (RFC 822 ou ISO) para YYYY-MM-DD; vazio se não parsear."""
    if not raw_date:
        return ""
    try:
        parsed = parsedate_to_datetime(raw_date)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            return ""
    return parsed.date().isoformat()


def _sort_key(parsed_date: Optional[datetime]) -> datetime:
    if parsed_date is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed_date.tzinfo is None:
        return parsed_date.replace(tzinfo=timezone.utc)
    return parsed_date


def parse_feed(content: bytes, source_name: str) -> List[Dict[str, Any]]:
    """Faz o parsing de um feed RSS/Atom em uma lista de notícias.

    Função pura (sem rede) para facilitar testes determinísticos.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        logger.warning("Feed inválido de %s: %s", source_name, exc)
        return []

    news: List[Dict[str, Any]] = []
    for item in root.findall(".//{*}item"):
        title = _element_text(item, "title")
        if not title or title.lower().startswith(_JUNK_TITLE_PREFIXES):
            continue

        raw_date = _element_text(item, "pubDate") or _element_text(item, "date")
        try:
            parsed_date = parsedate_to_datetime(raw_date) if raw_date else None
        except (TypeError, ValueError):
            parsed_date = None

        news.append(
            {
                "title": title,
                "summary": _clean_summary(_element_text(item, "description")),
                "source": source_name,
                "date": _normalize_date(raw_date),
                "url": _element_text(item, "link"),
                "_parsed_date": parsed_date,
            }
        )

    return news


def _relevance_score(item: Dict[str, Any]) -> int:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return sum(1 for term in RELEVANCE_TERMS if term in haystack)


class NewsSearchInput(BaseModel):
    """Input para a ferramenta de busca de notícias."""

    query: str = Field(
        default="SRAG síndrome respiratória aguda grave Brasil",
        description="Termo de busca para notícias (padrão: SRAG)",
    )
    max_results: int = Field(
        default=5,
        description="Número máximo de resultados (padrão: 5)",
    )


class NewsSearchTool(BaseTool):
    """Ferramenta para buscar notícias reais sobre SRAG e saúde pública."""

    name: str = "news_search"
    description: str = (
        "Busca notícias recentes sobre SRAG (Síndrome Respiratória Aguda Grave) "
        "e temas de saúde pública no Brasil a partir de feeds oficiais "
        "(Agência Fiocruz e Agência Brasil). Retorna título, resumo, fonte, "
        "data e URL das notícias encontradas."
    )
    args_schema: type[BaseModel] = NewsSearchInput
    feeds: List[Dict[str, str]] = Field(default_factory=lambda: list(DEFAULT_NEWS_FEEDS))
    timeout_seconds: float = 15.0

    def _fetch_feed(self, url: str) -> bytes:
        """Baixa o conteúdo bruto de um feed. Isolado para permitir mock em testes."""
        response = requests.get(
            url,
            timeout=self.timeout_seconds,
            headers=_REQUEST_HEADERS,
        )
        response.raise_for_status()
        return response.content

    def _collect(self, max_results: int) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        for feed in self.feeds:
            try:
                content = self._fetch_feed(feed["url"])
            except Exception as exc:  # rede indisponível, HTTP erro, timeout
                logger.warning("Falha ao buscar feed %s: %s", feed.get("name"), exc)
                continue
            collected.extend(parse_feed(content, feed.get("name", "Desconhecida")))

        # Dedupe por título normalizado, preservando a primeira ocorrência.
        seen = set()
        unique: List[Dict[str, Any]] = []
        for item in collected:
            key = re.sub(r"\s+", " ", item["title"].lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        # Ordena por relevância ao tema e, dentro disso, por data mais recente.
        unique.sort(
            key=lambda item: (
                _relevance_score(item),
                _sort_key(item.get("_parsed_date")),
            ),
            reverse=True,
        )

        top = unique[:max_results]
        for item in top:
            item.pop("_parsed_date", None)
        return top

    def _run(
        self,
        query: str = "SRAG síndrome respiratória aguda grave Brasil",
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Executa a busca de notícias reais nos feeds configurados."""
        logger.info("Buscando notícias sobre: %s", query)

        try:
            news = self._collect(max_results)
        except Exception as exc:  # falha inesperada de parsing/ordenação
            logger.error("Erro ao buscar notícias: %s", exc)
            return {"error": str(exc), "query": query, "news": []}

        logger.info("%d notícias encontradas", len(news))
        return {
            "query": query,
            "total_results": len(news),
            "news": news,
            "timestamp": datetime.now().isoformat(),
        }

    async def _arun(
        self,
        query: str = "SRAG",
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Versão assíncrona (não implementada)."""
        raise NotImplementedError("Versão assíncrona não implementada")


def create_news_tool(feeds: Optional[List[Dict[str, str]]] = None) -> NewsSearchTool:
    """Cria e retorna uma instância da ferramenta de notícias."""
    if feeds:
        return NewsSearchTool(feeds=list(feeds))
    return NewsSearchTool()


if __name__ == "__main__":
    tool = create_news_tool()

    print("\n=== Teste: Busca de Notícias Reais sobre SRAG ===")
    result = tool._run(max_results=5)

    print(f"\nQuery: {result.get('query')}")
    print(f"Total de resultados: {result.get('total_results', 0)}\n")

    for i, news_item in enumerate(result.get("news", []), 1):
        print(f"{i}. {news_item['title']}")
        print(f"   Fonte: {news_item['source']} | Data: {news_item['date']}")
        print(f"   {news_item['summary'][:120]}")
        print(f"   {news_item['url']}")
        print()
