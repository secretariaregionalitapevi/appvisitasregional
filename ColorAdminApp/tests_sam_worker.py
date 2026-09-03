from django.test import SimpleTestCase
from unittest.mock import Mock, patch

from .management.commands.run_sam_sync_worker import (
    DEFAULT_IDLE_INTERVAL_SECONDS,
    MIN_IDLE_INTERVAL_SECONDS,
    Command,
)


class SamWorkerValidationTests(SimpleTestCase):
    def setUp(self):
        self.report = {
            "student": "Aluno",
            "tabs": {name: {"tables": [{"headers": [], "rows": []}]} for name in (
                "MSA", "Método", "Hinário", "Provas", "Escalas"
            )},
        }
        self.document = {"students": [{"history": {
            "msa": [{"data_aula": "2026-08-01"}], "metodo": [], "hinario": [],
            "provas": [], "escalas": [], "atividades": [],
        }}]}

    def test_accepts_history_only_after_all_events_are_reconciled(self):
        count = Command._validate_history(self.report, self.document, {
            "statistics": {"linked": 1, "new_events": 1},
        })
        self.assertEqual(count, 1)

    def test_rejects_tab_extraction_error(self):
        self.report["tabs"]["MSA"] = {"tables": [], "error": "timeout"}
        with self.assertRaisesRegex(RuntimeError, "Extração incompleta"):
            Command._validate_history(self.report, self.document)

    def test_rejects_import_that_silently_loses_events(self):
        with self.assertRaisesRegex(RuntimeError, "1 evento.*0 conciliado"):
            Command._validate_history(self.report, self.document, {
                "statistics": {"linked": 1},
            })

    @patch("ColorAdminApp.management.commands.run_sam_sync_worker.requests.get")
    def test_pending_queue_ignores_students_missing_from_current_catalog(self, get):
        response = Mock()
        response.json.return_value = []
        response.raise_for_status.return_value = None
        get.return_value = response

        Command()._pending(100)

        self.assertEqual(get.call_args.kwargs["params"]["missing_since"], "is.null")

    def test_idle_discovery_interval_is_fast_but_rate_limited(self):
        self.assertEqual(DEFAULT_IDLE_INTERVAL_SECONDS, 120)
        self.assertEqual(MIN_IDLE_INTERVAL_SECONDS, 60)
