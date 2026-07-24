"""Testes da configuração da aplicação (src/config.py)."""

import os
import unittest
from unittest import mock

import tests.conftest  # noqa: F401  garante src/ no sys.path
from config import DEFAULT_NEWS_FEEDS, AppConfig, _parse_news_feeds


class TestNewsFeedsConfig(unittest.TestCase):
    def test_default_when_env_absent(self):
        feeds = _parse_news_feeds(None)
        self.assertEqual(feeds, DEFAULT_NEWS_FEEDS)
        # Retorna cópia: mutação não afeta o default.
        feeds[0]["name"] = "alterado"
        self.assertNotEqual(DEFAULT_NEWS_FEEDS[0]["name"], "alterado")

    def test_parses_json_objects(self):
        raw = '[{"name":"Fonte A","url":"https://a.test/rss"}]'
        self.assertEqual(
            _parse_news_feeds(raw),
            [{"name": "Fonte A", "url": "https://a.test/rss"}],
        )

    def test_parses_list_of_urls_deriving_name_from_host(self):
        feeds = _parse_news_feeds('["https://a.test/rss"]')
        self.assertEqual(feeds, [{"name": "a.test", "url": "https://a.test/rss"}])

    def test_invalid_json_falls_back_to_default(self):
        self.assertEqual(_parse_news_feeds("{not json"), DEFAULT_NEWS_FEEDS)

    def test_empty_list_falls_back_to_default(self):
        self.assertEqual(_parse_news_feeds("[]"), DEFAULT_NEWS_FEEDS)

    def test_from_env_reads_srag_news_feeds(self):
        raw = '[{"name":"Fonte B","url":"https://b.test/rss"}]'
        with mock.patch.dict(os.environ, {"SRAG_NEWS_FEEDS": raw}, clear=False):
            config = AppConfig.from_env()
        self.assertEqual(config.news_feeds, [{"name": "Fonte B", "url": "https://b.test/rss"}])


if __name__ == "__main__":
    unittest.main()
