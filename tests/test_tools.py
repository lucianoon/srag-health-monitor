"""Testes das ferramentas (src/tools): banco, notícias e gráficos."""

import json
import os
import tempfile
import unittest

import requests

from tests.conftest import TempSRAGDatabaseMixin, offline_news_guard
from tools.chart_tool import create_chart_tool
from tools.database_tool import DatabaseQueryTool
from tools.news_tool import create_news_tool, parse_feed

# Segurança extra: nenhum teste deste módulo deve tocar a rede. Os testes de
# parsing/ranking injetam seu próprio fetch por instância.
setUpModule, tearDownModule = offline_news_guard()


class TestDatabaseTool(TempSRAGDatabaseMixin, unittest.TestCase):
    """Testes para a ferramenta de consulta ao banco."""

    def setUp(self):
        super().setUp()
        self.tool = DatabaseQueryTool(db_path=self.db_path)

    def test_query_metrics(self):
        result = self.tool._run(query_type="metrics")
        self.assertIn("taxa_aumento_casos", result)
        self.assertIn("taxa_mortalidade", result)
        self.assertIn("taxa_ocupacao_uti", result)
        self.assertIn("taxa_vacinacao", result)

    def test_query_daily_cases(self):
        result = self.tool._run(query_type="daily_cases", days=7)
        self.assertIn("daily_cases", result)
        self.assertIsInstance(result["daily_cases"], list)

    def test_query_monthly_cases(self):
        result = self.tool._run(query_type="monthly_cases", months=3)
        self.assertIn("monthly_cases", result)
        self.assertIsInstance(result["monthly_cases"], list)


SAMPLE_FIOCRUZ_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Agencia Fiocruz</title>
    <item>
      <title>Nav. ed. pt Bibliotecas</title>
      <link>https://agencia.fiocruz.br/nav</link>
      <pubDate>Thu, 02 Jul 2026 18:05:40 +0000</pubDate>
      <description>menu de navegacao</description>
    </item>
    <item>
      <title>InfoGripe alerta para alta de casos de SRAG no pais</title>
      <link>https://agencia.fiocruz.br/infogripe-srag</link>
      <pubDate>Thu, 02 Jul 2026 14:07:27 +0000</pubDate>
      <description>&lt;p&gt;Boletim aponta &lt;b&gt;aumento&lt;/b&gt; de casos de SRAG.&lt;/p&gt;</description>
    </item>
    <item>
      <title>Fiocruz inaugura novo predio administrativo</title>
      <link>https://agencia.fiocruz.br/predio</link>
      <pubDate>Wed, 01 Jul 2026 10:00:00 +0000</pubDate>
      <description>Nota institucional sem relacao com epidemiologia.</description>
    </item>
  </channel>
</rss>"""


class TestNewsFeedParsing(unittest.TestCase):
    def test_parse_feed_strips_html_and_normalizes_date(self):
        items = parse_feed(SAMPLE_FIOCRUZ_FEED, "Agência Fiocruz")
        titles = [item["title"] for item in items]

        self.assertNotIn("Nav. ed. pt Bibliotecas", titles)  # item de navegação filtrado
        srag_item = next(item for item in items if "InfoGripe" in item["title"])
        self.assertEqual(srag_item["source"], "Agência Fiocruz")
        self.assertEqual(srag_item["date"], "2026-07-02")
        self.assertNotIn("<", srag_item["summary"])  # HTML removido
        self.assertIn("SRAG", srag_item["summary"])
        self.assertTrue(srag_item["url"].startswith("https://"))


class TestNewsTool(unittest.TestCase):
    def _tool_with_feed(self, content):
        tool = create_news_tool()
        tool.feeds = [{"name": "Fonte Teste", "url": "https://example.test/feed"}]
        tool._fetch_feed = lambda url: content
        return tool

    def test_search_news_ranks_relevant_items_first(self):
        tool = self._tool_with_feed(SAMPLE_FIOCRUZ_FEED)
        result = tool._run(max_results=3)

        self.assertIn("news", result)
        self.assertIn("total_results", result)
        # 2 itens válidos (o de navegação é filtrado); o de SRAG vem primeiro.
        self.assertEqual(len(result["news"]), 2)
        self.assertIn("SRAG", result["news"][0]["title"])

    def test_news_structure(self):
        tool = self._tool_with_feed(SAMPLE_FIOCRUZ_FEED)
        result = tool._run(max_results=1)
        news_item = result["news"][0]
        for key in ("title", "summary", "source", "date", "url"):
            self.assertIn(key, news_item)

    def test_search_news_degrades_gracefully_on_fetch_failure(self):
        def failing_fetch(url):
            raise requests.RequestException("rede indisponível")

        tool = create_news_tool()
        tool._fetch_feed = failing_fetch
        result = tool._run(max_results=5)

        # Sem rede, retorna lista vazia sem fabricar notícias.
        self.assertEqual(result["news"], [])
        self.assertEqual(result["total_results"], 0)


class TestChartTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmpdir.name)
        self.tool = create_chart_tool()

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmpdir.cleanup()

    def test_generate_daily_chart(self):
        data = [
            {"date": "2024-12-01", "cases": 100},
            {"date": "2024-12-02", "cases": 150},
        ]
        result = self.tool._run(chart_type="daily", data=json.dumps(data))
        self.assertTrue(result["success"])
        self.assertIn("filename", result)

    def test_generate_monthly_chart(self):
        data = [
            {"month": "2024-10", "cases": 1000},
            {"month": "2024-11", "cases": 1200},
        ]
        result = self.tool._run(chart_type="monthly", data=json.dumps(data))
        self.assertTrue(result["success"])
        self.assertIn("filename", result)


if __name__ == "__main__":
    unittest.main()
