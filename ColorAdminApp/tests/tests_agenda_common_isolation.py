import json
from unittest.mock import Mock, patch
from django.test import RequestFactory, SimpleTestCase
from ColorAdminApp.views import apiVisitasAgenda


class AgendaCommonIsolationTests(SimpleTestCase):
    @patch('ColorAdminApp.views.requests.patch')
    @patch('ColorAdminApp.views.supabase_get')
    @patch('ColorAdminApp.views.visible_commons', return_value=[
        {'comum': 'COMUM A', 'cidade': 'ITAPEVI'},
        {'comum': 'COMUM B', 'cidade': 'ITAPEVI'},
    ])
    @patch('ColorAdminApp.views.user_scope', return_value={'level': 'global'})
    def test_known_member_from_other_common_is_never_reassigned(self, scope, catalog, get, update):
        agenda = Mock()
        agenda.json.return_value = [{
            'id': 'visit-b', 'irmandade_id': 'member-b', 'comum': 'COMUM A',
            'titulo': 'Maria', 'endereco_visitado': 'Rua A, 10', 'status': 'Realizada',
        }]
        members = Mock()
        members.json.return_value = [
            {'id': 'member-a', 'comum': 'COMUM A', 'nome': 'Maria', 'endereco': 'Rua A, 10'},
            {'id': 'member-b', 'comum': 'COMUM B', 'nome': 'Maria', 'endereco': 'Rua A, 10'},
        ]
        get.side_effect = [agenda, members]
        request = RequestFactory().get('/visitas/api/agenda/', {'comum': 'COMUM A'})
        request.session = {'user_profile': {'role_id': 1}}
        response = apiVisitasAgenda(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), [])
        update.assert_not_called()
