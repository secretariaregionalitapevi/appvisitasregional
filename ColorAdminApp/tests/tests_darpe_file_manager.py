import json
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from ColorAdminApp.modules import darpe_file_manager as fm
from ColorAdminApp.tests.tests_darpe_library import request, pdf


class DarpeFileManagerTests(SimpleTestCase):
    def current(self):
        return {'id': 'documento', 'version': 3, 'titulo': 'Instrumentos', 'object_path': 'original.pdf', 'deleted_at': None}

    @patch.object(fm.library, 'can_publish', return_value=False)
    @patch.object(fm.requests, 'patch')
    def test_read_only_profile_cannot_edit(self, update, allowed):
        self.assertEqual(fm.update(request('post', level='local'), 'documento').status_code, 403)
        update.assert_not_called()

    @patch.object(fm.library, 'can_publish', return_value=True)
    @patch.object(fm, 'record')
    @patch.object(fm.requests, 'patch')
    def test_stale_editor_does_not_write(self, update, record, allowed):
        record.return_value = self.current()
        response = fm.update(request('post', {'version': '2', 'action': 'archive'}), 'documento')
        self.assertEqual(response.status_code, 409)
        update.assert_not_called()

    @patch.object(fm.library, 'can_publish', return_value=True)
    @patch.object(fm, 'record')
    @patch.object(fm.requests, 'patch')
    def test_archive_is_reversible_and_compares_version(self, update, record, allowed):
        record.return_value = self.current()
        update.return_value = Mock(json=lambda: [{'id': 'documento', 'version': 4}])
        self.assertEqual(fm.update(request('post', {'version': '3', 'action': 'archive'}), 'documento').status_code, 200)
        call = update.call_args.kwargs
        self.assertIn('deleted_at', call['json'])
        self.assertEqual(call['params']['version'], 'eq.3')
        self.assertNotIn('object_path', call['json'])
        self.assertEqual(fm.update(request('post', {'version': '3', 'action': 'restore'}), 'documento').status_code, 200)
        self.assertIsNone(update.call_args.kwargs['json']['deleted_at'])

    @patch.object(fm.library, 'can_publish', return_value=True)
    @patch.object(fm, 'folder', return_value={'id': 'destino'})
    @patch.object(fm, 'record')
    @patch.object(fm.requests, 'post')
    @patch.object(fm.requests, 'patch')
    def test_replacement_uses_new_object_and_keeps_original(self, update, upload, record, folder, allowed):
        record.return_value = self.current()
        update.return_value = Mock(json=lambda: [{'id': 'documento', 'version': 4}])
        req = request('post', {'version': '3', 'action': 'edit', 'titulo': 'Nova orientação', 'descricao': 'Revista', 'original_name': 'novo.pdf', 'pasta_id': 'destino', 'arquivo': pdf()})
        self.assertEqual(fm.update(req, 'documento').status_code, 200)
        data = update.call_args.kwargs['json']
        self.assertNotEqual(data['object_path'], 'original.pdf')
        self.assertNotIn('x-upsert', upload.call_args.kwargs['headers'])
        self.assertEqual(data['updated_by'], 'gestor')

    @patch.object(fm.library, 'can_publish', return_value=True)
    @patch.object(fm, 'folder', return_value={'id': 'destino'})
    @patch.object(fm, 'record')
    @patch.object(fm.requests, 'post')
    @patch.object(fm.requests, 'patch')
    @patch.object(fm.requests, 'delete')
    def test_race_after_upload_cleans_only_unreferenced_new_object(self, delete, update, upload, record, folder, allowed):
        record.return_value = self.current()
        update.return_value = Mock(json=lambda: [])
        req = request('post', {'version': '3', 'titulo': 'Novo', 'original_name': 'novo.pdf', 'pasta_id': 'destino', 'arquivo': pdf()})
        self.assertEqual(fm.update(req, 'documento').status_code, 409)
        self.assertNotIn('original.pdf', delete.call_args.args[0])

    def test_unsafe_filename_rejected(self):
        for name in ['../arquivo.pdf', 'pasta\\arquivo.pdf', 'arquivo.html', 'arquivo\n.pdf']:
            with self.assertRaises(ValueError):
                fm.metadata({'titulo': 'Título', 'original_name': name})

    @patch.object(fm.library, 'allowed', return_value=True)
    @patch.object(fm, 'record')
    @patch.object(fm, 'read')
    def test_versions_hide_internal_object_paths(self, read, record, allowed):
        record.return_value = self.current()
        read.return_value = [{'id': 'revision', 'version': 1, 'created_at': '2026-11-05', 'snapshot': {'object_path': 'private.pdf', 'created_by': 'operador', 'titulo': 'Orientação'}}]
        response = fm.versions(request(), 'documento')
        data = json.loads(response.content)['items'][0]
        self.assertNotIn('object_path', data)
        self.assertNotIn('created_by', data)
        self.assertEqual(data['titulo'], 'Orientação')

    @patch.object(fm.library, 'allowed', return_value=True)
    @patch.object(fm, 'record')
    @patch.object(fm, 'read')
    def test_local_reader_cannot_read_archived_history(self, read, record, allowed):
        record.return_value = {**self.current(), 'deleted_at': '2026-11-05'}
        self.assertEqual(fm.versions(request(level='local'), 'documento').status_code, 404)
        read.assert_not_called()

    @patch.object(fm.library, 'can_publish', return_value=True)
    @patch.object(fm, 'record')
    @patch.object(fm, 'read')
    @patch.object(fm.requests, 'patch')
    def test_restore_version_uses_saved_snapshot_as_new_revision(self, update, read, record, allowed):
        record.return_value = self.current()
        snapshot = {'titulo': 'Antigo', 'descricao': 'Texto anterior', 'original_name': 'antigo.pdf', 'byte_size': 100, 'object_path': 'historico.pdf', 'pasta_id': 'pasta-anterior', 'version': 1, 'created_by': 'outro'}
        read.return_value = [{'snapshot': snapshot}]
        update.return_value = Mock(json=lambda: [{'id': 'documento', 'version': 4}])
        response = fm.update(request('post', {'version': '3', 'action': 'restore_version', 'revision_id': '00000000-0000-4000-8000-000000000009'}), 'documento')
        self.assertEqual(response.status_code, 200)
        data = update.call_args.kwargs['json']
        self.assertEqual(data['object_path'], 'historico.pdf')
        self.assertNotIn('version', data)
        self.assertNotIn('created_by', data)
        self.assertEqual(read.call_args.args[1]['documento_id'], 'eq.documento')
