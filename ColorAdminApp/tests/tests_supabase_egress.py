from unittest.mock import Mock, patch
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from ColorAdminApp.management.commands.sync_sam_classes import Command
from ColorAdminApp.utils.supabase_http import supabase_get
from ColorAdminApp.management.commands.run_sam_sync_worker import Command as Worker


class SupabaseEgressTests(SimpleTestCase):
    def test_daily_limit_survives_restart_and_short_interval_override(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'daily.json'
            self.assertEqual(Worker._daily_wait(path, 60, 100000), 0)
            Worker._claim_daily_cycle(path, 100000)
            self.assertEqual(Worker()._daily_wait(path, 60, 103600), 82800)
            self.assertEqual(Worker()._daily_wait(path, 60, 186400), 0)

    def test_incremental_classes_do_not_download_attendance_table(self):
        command = Command()
        with patch.object(command, '_get_all') as read:
            self.assertEqual(command._completed_class_ids(False), set())
        read.assert_not_called()

    def test_full_classes_keep_resume_detection(self):
        command = Command()
        with patch.object(command, '_get_all', return_value=[{'aula_id': 'a'}, {'aula_id': 'a'}, {'aula_id': 'b'}]):
            self.assertEqual(command._completed_class_ids(True), {'a', 'b'})

    def test_read_metrics_do_not_log_query_or_credentials(self):
        response = Mock(status_code=200, headers={'Content-Length': '120'})
        client = Mock()
        client.get.return_value = response
        with self.assertLogs('ColorAdminApp.utils.supabase_http', level='INFO') as logs:
            self.assertIs(supabase_get('https://example.test/rest/v1/students?token=secret', session=client,
                                     headers={'Authorization': 'Bearer private'}), response)
        output = '\n'.join(logs.output)
        self.assertIn('response_bytes=120', output)
        self.assertNotIn('secret', output)
        self.assertNotIn('private', output)
