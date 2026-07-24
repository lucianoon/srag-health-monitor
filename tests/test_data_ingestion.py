"""Testes do serviço de ingestão de dados SUS (src/services/data_ingestion_service.py)."""

import tempfile
import unittest
from unittest import mock

from tests.conftest import make_app_config  # também garante src/ no sys.path
from database.db_manager import SRAGDatabase
from services.data_ingestion_service import DataIngestionService


class TestDataIngestionService(unittest.TestCase):
    def test_ingestion_downloads_processes_and_loads_sqlite_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_app_config(
                tmpdir,
                sus_data_url="https://dadosabertos.saude.gov.br/srag.csv",
            )
            csv_bytes = self._sample_srag_csv().encode("latin1")

            response = mock.Mock()
            response.raise_for_status.return_value = None
            response.iter_content.return_value = [csv_bytes]

            with mock.patch(
                "services.data_ingestion_service.requests.get",
                return_value=response,
            ):
                result = DataIngestionService(config).run()

            db = SRAGDatabase(str(config.db_path))
            db.connect()
            try:
                total_cases = db.get_total_cases()
            finally:
                db.close()

            self.assertEqual(result.rows_processed, 2)
            self.assertEqual(total_cases, 2)
            self.assertTrue(result.metadata_path.exists())

    @staticmethod
    def _sample_srag_csv() -> str:
        header = [
            "DT_NOTIFIC", "DT_SIN_PRI", "SG_UF", "CO_MUN_RES", "CS_SEXO",
            "NU_IDADE_N", "TP_IDADE", "EVOLUCAO", "UTI", "DT_ENTUTI",
            "DT_SAIDUTI", "VACINA", "VACINA_COV", "DOSE_1_COV",
            "DOSE_2_COV", "DOSE_REF", "CLASSI_FIN", "DT_EVOLUCA",
            "DT_INTERNA", "HOSPITAL", "FEBRE", "TOSSE", "DISPNEIA",
            "SATURACAO",
        ]
        rows = [
            [
                "2024-01-01", "2023-12-30", "SP", "355030", "1", "40",
                "4", "1", "2", "", "", "1", "2", "", "", "", "5",
                "2024-01-05", "2024-01-02", "1", "1", "1", "2", "2",
            ],
            [
                "2024-01-02", "2023-12-31", "RJ", "330455", "2", "70",
                "4", "2", "1", "2024-01-03", "2024-01-07", "2", "1",
                "", "", "", "5", "2024-01-08", "2024-01-02", "1",
                "1", "1", "1", "1",
            ],
        ]
        lines = [";".join(header)]
        lines.extend(";".join(row) for row in rows)
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
