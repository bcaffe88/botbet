import os
import unittest
from unittest.mock import patch

# Garantir env necessários antes de importar módulos que validam variáveis
os.environ.setdefault("FOOTBALL_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgres://user:pass@localhost/db")

import estatisticas_time as et  # noqa: E402


class FakeCursor:
    def __init__(self, executed):
        self.executed = executed

    def execute(self, sql, params=None):
        self.executed.append(sql)


class FakeConn:
    def __init__(self, executed):
        self.executed = executed

    def cursor(self):
        return FakeCursor(self.executed)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class HistoricoTests(unittest.TestCase):
    def test_calcular_bonus_historico(self):
        bonus, criterios = et.calcular_bonus_historico(0.7, None, 0.65, 0.5, 0.5)
        self.assertEqual(bonus, 1)
        self.assertIn("Histórico próprio favorável", criterios)

        bonus, criterios = et.calcular_bonus_historico(0.55, "RED", 0.65, 0.5, 0.5)
        self.assertEqual(bonus, 0.0)  # 0.5 - 0.5
        self.assertIn("Histórico próprio moderado", criterios)
        self.assertIn("Alerta RED recente", criterios)

    def test_init_db_executes_schema(self):
        executed = []
        fake_conn = FakeConn(executed)
        with patch.object(et, "_get_conn", return_value=fake_conn), patch.object(et, "usar_postgres", return_value=True):
            et.init_db()

        self.assertTrue(any("historico_resumos" in sql for sql in executed))
        self.assertTrue(any("fixtures_cache" in sql for sql in executed))


if __name__ == "__main__":
    unittest.main()
