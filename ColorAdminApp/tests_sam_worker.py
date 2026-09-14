from django.test import SimpleTestCase
from unittest.mock import Mock, patch

from .management.commands.run_sam_sync_worker import (
    DEFAULT_CLASSES_INTERVAL_SECONDS,
    DEFAULT_IDLE_INTERVAL_SECONDS,
    MIN_CLASSES_INTERVAL_SECONDS,
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
        self.assertEqual(DEFAULT_CLASSES_INTERVAL_SECONDS, 300)
        self.assertEqual(MIN_CLASSES_INTERVAL_SECONDS, 120)

    @patch("ColorAdminApp.management.commands.run_sam_sync_worker.call_command")
    def test_worker_runs_incremental_classes_with_short_lookback(self, call_command):
        command = Command()
        command._sync_classes("C:/scraper", 14)

        call_command.assert_called_once_with(
            "sync_sam_classes", scraper_dir="C:/scraper", lookback_days=14,
            stdout=command.stdout, stderr=command.stderr,
        )

    @patch("ColorAdminApp.management.commands.run_sam_sync_worker.requests.get")
    def test_old_synced_histories_fill_remaining_batch(self, get):
        first, old = Mock(), Mock()
        first.json.return_value = [{"id": "pending"}]
        old.json.return_value = [{"id": "old"}]
        get.side_effect = [first, old]
        self.assertEqual(Command()._pending(3), [{"id": "pending"}, {"id": "old"}])
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["sync_status"], "eq.synced")
        self.assertEqual(params["limit"], 2)
        self.assertIn("last_history_sync_at.lt.", params["or"])
        self.assertEqual(params["aluno_id"], "not.is.null")
        self.assertEqual(params["missing_since"], "is.null")

    @patch("ColorAdminApp.management.commands.run_sam_sync_worker.requests.get")
    def test_pending_histories_take_priority_over_periodic_refresh(self, get):
        get.return_value.json.return_value = [{"id": "pending"}]
        self.assertEqual(Command()._pending(1), [{"id": "pending"}])
        self.assertEqual(get.call_count, 1)

    def test_refresh_summary_counts_recent_updates_not_total_coverage(self):
        from datetime import datetime, timezone, timedelta
        from .gem_sync_admin import _history_refresh_summary
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=1)).isoformat()
        result = _history_refresh_summary([
            {"last_history_sync_at": recent},
            {"last_history_sync_at": (now - timedelta(days=2)).isoformat()},
            {"last_history_sync_at": None},
            {"last_history_sync_at": "invalid"},
        ])
        self.assertEqual(result["refreshed_last_24h"], 1)
        self.assertEqual(result["last_history_sync_at"], recent)
