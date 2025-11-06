"""Ferramenta de busca de notícias sobre SRAG."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import logging
import os
import re
from typing import Any, Dict, Iterable, List
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from .base import ToolBase

logger = logging.getLogger(__name__)


DEFAULT_RSS_URL = (
    "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
)


@dataclass
class NewsSearchInput:
    """Estrutura de entrada para documentação da ferramenta."""

    query: str = "SRAG síndrome respiratória aguda grave Brasil"
    max_results: int = 5


class NewsSearchTool(ToolBase):
    """Ferramenta para buscar notícias sobre SRAG."""

    name: str = "news_search"
    description: str = (
        "Busca notícias recentes sobre SRAG (Síndrome Respiratória Aguda Grave) "
        "em fontes públicas. Retorna título, resumo, fonte e data das notícias "
        "encontradas, com fallback automático para conteúdo simulado caso a "
        "consulta em tempo real falhe."
    )
    args_schema: type[NewsSearchInput] = NewsSearchInput

    def __init__(self, *, rss_url: str | None = None, request_timeout: float = 10.0) -> None:
        super().__init__()
        self.rss_url_template = rss_url or os.getenv("SRAG_NEWS_RSS_URL", DEFAULT_RSS_URL)
        timeout_env = os.getenv("SRAG_NEWS_TIMEOUT")
        self.request_timeout = float(timeout_env) if timeout_env else float(request_timeout)

    # -------------------------- Internal helpers -------------------------
    def _build_feed_url(self, query: str) -> str:
        encoded_query = quote_plus(query)
        return self.rss_url_template.format(query=encoded_query)

    @staticmethod
    def _clean_text(value: str | None) -> str:
        if not value:
            return ""
        no_tags = re.sub(r"<[^>]+>", " ", value)
        compact = re.sub(r"\s+", " ", no_tags).strip()
        return compact

    @staticmethod
    def _extract_source(url: str | None, fallback: str = "Fonte não informada") -> str:
        if url:
            parsed = urlparse(url)
            if parsed.netloc:
                return parsed.netloc.replace("www.", "")
        return fallback

    def _parse_items(self, xml_text: str, max_results: int) -> List[Dict[str, str]]:
        root = ET.fromstring(xml_text)
        channel_items: Iterable[ET.Element] = root.findall(".//item")

        news_items: List[Dict[str, str]] = []
        for item in channel_items:
            title = self._clean_text(item.findtext("title"))
            description = self._clean_text(item.findtext("description"))
            link = (item.findtext("link") or "").strip()
            source_tag = item.find("source")
            source = (
                self._clean_text(source_tag.text)
                if source_tag is not None and source_tag.text
                else self._extract_source(link)
            )

            published_raw = item.findtext("pubDate") or ""
            try:
                published_dt = parsedate_to_datetime(published_raw)
                if published_dt is not None:
                    published = published_dt.strftime("%Y-%m-%d")
                else:
                    raise ValueError("Data inválida")
            except Exception:  # noqa: BLE001 - fallback controlado
                published = datetime.now(UTC).strftime("%Y-%m-%d")

            news_items.append(
                {
                    "title": title or "Notícia sem título",
                    "summary": description or "Sem resumo disponível.",
                    "source": source,
                    "date": published,
                    "url": link,
                }
            )

            if len(news_items) >= max_results:
                break

        return news_items

    def _fetch_live_news(self, query: str, max_results: int) -> List[Dict[str, str]]:
        url = self._build_feed_url(query)
        logger.debug("Buscando notícias em %s", url)

        request = Request(url, headers={"User-Agent": "SRAGHealthMonitor/1.0"})

        with urlopen(request, timeout=self.request_timeout) as response:  # noqa: S310 - URL controlada
            xml_bytes = response.read()

        xml_text = xml_bytes.decode("utf-8", errors="ignore")
        news = self._parse_items(xml_text, max_results)
        return news

    @staticmethod
    def _fallback_news(max_results: int) -> List[Dict[str, str]]:
        now = datetime.now(UTC)
        simulated = [
            {
                "title": "SRAG: autoridades reforçam vigilância em capitais brasileiras",
                "summary": (
                    "Secretarias estaduais de Saúde ampliam o monitoramento de vírus respiratórios após incremento "
                    "nos atendimentos por síndrome respiratória aguda grave nas últimas semanas."
                ),
                "source": "Simulação SRAG",
                "date": (now).strftime("%Y-%m-%d"),
                "url": "",
            },
            {
                "title": "Campanhas de vacinação ganham reforço para conter casos graves",
                "summary": (
                    "Esforço conjunto entre municípios busca elevar a cobertura de vacinação contra gripe e COVID-19, "
                    "priorizando grupos vulneráveis e profissionais de saúde."
                ),
                "source": "Simulação SRAG",
                "date": (now).strftime("%Y-%m-%d"),
                "url": "",
            },
            {
                "title": "Hospitais reorganizam leitos de UTI diante da sazonalidade",
                "summary": (
                    "Unidades hospitalares ajustam a disponibilidade de leitos para antecipar possíveis picos de "
                    "demandas por SRAG durante o período de maior circulação viral."
                ),
                "source": "Simulação SRAG",
                "date": (now).strftime("%Y-%m-%d"),
                "url": "",
            },
        ]
        return simulated[:max_results]

    # ------------------------------- Public API -------------------------------
    def _run(self, query: str = "SRAG síndrome respiratória aguda grave Brasil", max_results: int = 5) -> Dict[str, Any]:
        """Executa a busca de notícias."""

        logger.info("Buscando notícias sobre: %s", query)
        metadata: Dict[str, Any] = {
            "query": query,
            "timestamp": datetime.now(UTC).isoformat(),
            "source_feed": self.rss_url_template,
            "fallback": False,
        }

        try:
            news = self._fetch_live_news(query, max_results)
            if not news:
                raise ValueError("Feed sem notícias para o termo informado")
        except Exception as exc:  # noqa: BLE001 - queremos capturar exceções de rede/parsing
            logger.warning("Falha ao buscar notícias em tempo real: %s", exc)
            metadata["fallback"] = True
            metadata["error"] = str(exc)
            news = self._fallback_news(max_results)

        metadata["total_results"] = len(news)
        metadata["news"] = news

        logger.info("%s notícias retornadas (fallback=%s)", len(news), metadata["fallback"])
        return metadata

    async def _arun(self, query: str = "SRAG", max_results: int = 5) -> Dict[str, Any]:
        """Versão assíncrona (não implementada)."""
        raise NotImplementedError("Versão assíncrona não implementada")


def create_news_tool() -> NewsSearchTool:
    """Cria e retorna uma instância da ferramenta de notícias."""

    return NewsSearchTool()


if __name__ == "__main__":
    tool = create_news_tool()

    print("\n=== Teste: Busca de Notícias sobre SRAG ===")
    result = tool._run(max_results=3)

    print(f"\nQuery: {result['query']}")
    print(f"Total de resultados: {result['total_results']} (fallback={result['fallback']})\n")

    for i, news_item in enumerate(result['news'], 1):
        print(f"{i}. {news_item['title']}")
        print(f"   Fonte: {news_item['source']} | Data: {news_item['date']}")
        print(f"   {news_item['summary'][:100]}...")
        print()
