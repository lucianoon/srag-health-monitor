"""Testes da configuração da aplicação (src/config.py)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tests.conftest  # noqa: F401  garante src/ no sys.path
from config import (
    DEFAULT_NEWS_FEEDS,
    AppConfig,
    UnsafePathError,
    _parse_news_feeds,
    ensure_within,
    resolve_within,
)

# Tentativas de sair do diretório base: absolutos (POSIX, Windows, UNC,
# drive-relativo), ".." em qualquer separador e byte nulo.
UNSAFE_PATHS = [
    "../fora.db",
    "sub/../../fora.db",
    "..\\..\\fora.db",
    "/etc/passwd",
    "C:\\Windows\\win.ini",
    "C:fora.db",
    "\\\\servidor\\share\\fora.db",
    "//servidor/share/fora.db",
    "srag.db\x00.txt",
    "",
]


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


class TestClientPaths(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.base = Path(self.tmpdir.name) / "base"
        self.base.mkdir()

    def test_relative_path_resolves_inside_base(self):
        resolved = resolve_within(self.base, "sub/srag.db")
        self.assertEqual(resolved, (self.base / "sub" / "srag.db").resolve())

    def test_rejects_traversal_and_absolute_paths(self):
        for value in UNSAFE_PATHS:
            with self.subTest(value=value), self.assertRaises(UnsafePathError):
                resolve_within(self.base, value)

    def test_rejects_symlink_pointing_outside_base(self):
        outside = Path(self.tmpdir.name) / "fora"
        outside.mkdir()
        link = self.base / "atalho"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink indisponível neste ambiente: {exc}")

        with self.assertRaises(UnsafePathError):
            resolve_within(self.base, "atalho/srag.db")

    def test_ensure_within_accepts_stored_absolute_path_inside_base(self):
        stored = self.base / "sub" / "relatorio.md"
        self.assertEqual(ensure_within(self.base, stored), stored.resolve())
        self.assertEqual(ensure_within(self.base, "sub/relatorio.md"), stored.resolve())

    def test_ensure_within_rejects_stored_paths_outside_base(self):
        for stored in (
            Path(self.tmpdir.name) / "fora.md",
            self.base / ".." / "fora.md",
            "../fora.md",
            "",
        ):
            with self.subTest(stored=str(stored)), self.assertRaises(UnsafePathError):
                ensure_within(self.base, stored)

    def test_for_client_request_confines_paths_to_server_dirs(self):
        data_dir = Path(self.tmpdir.name) / "data"
        reports_dir = Path(self.tmpdir.name) / "reports"
        env = {"SRAG_DATA_DIR": str(data_dir), "SRAG_OUTPUT_DIR": str(reports_dir)}
        with mock.patch.dict(os.environ, env, clear=False):
            config = AppConfig.for_client_request(db_path="srag.db", output_dir="equipe-a")
            default = AppConfig.for_client_request()

            with self.assertRaises(UnsafePathError):
                AppConfig.for_client_request(db_path=str(Path(self.tmpdir.name) / "x.db"))
            with self.assertRaises(UnsafePathError):
                AppConfig.for_client_request(output_dir="../fora")

        self.assertEqual(config.db_path, (data_dir / "srag.db").resolve())
        self.assertEqual(config.reports_dir, (reports_dir / "equipe-a").resolve())
        self.assertEqual(default.reports_dir, reports_dir)


if __name__ == "__main__":
    unittest.main()
