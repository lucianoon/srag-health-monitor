"""Testes do gerenciador de banco de dados (src/database/db_manager.py)."""

import unittest

from tests.conftest import TempSRAGDatabaseMixin


class TestDatabaseManager(TempSRAGDatabaseMixin, unittest.TestCase):
    """Testes para o gerenciador de banco de dados."""

    def test_get_total_cases(self):
        total = self.db.get_total_cases()
        self.assertEqual(total, 12)

    def test_get_mortality_rate(self):
        rate = self.db.get_mortality_rate()
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)

    def test_get_uti_occupation_rate(self):
        rate = self.db.get_uti_occupation_rate()
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)

    def test_get_vaccination_rate(self):
        rate = self.db.get_vaccination_rate()
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)


if __name__ == "__main__":
    unittest.main()
