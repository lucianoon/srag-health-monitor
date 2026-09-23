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

    def test_get_icu_admission_proportion(self):
        # Amostra: 12 casos, internou_uti=1 quando i % 3 == 0 (4 casos).
        proportion = self.db.get_icu_admission_proportion()
        self.assertAlmostEqual(proportion, 4 / 12 * 100)

    def test_all_metrics_label_icu_indicator_as_case_proportion(self):
        metrics = self.db.get_all_metrics()
        self.assertIn("proporcao_casos_uti", metrics)
        self.assertNotIn("taxa_ocupacao_uti", metrics)

    def test_get_vaccination_rate(self):
        rate = self.db.get_vaccination_rate()
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)


if __name__ == "__main__":
    unittest.main()
