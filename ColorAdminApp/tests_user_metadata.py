import json
from unittest.mock import patch
from django.test import RequestFactory, SimpleTestCase
from . import admin_views

class UserMetadataTests(SimpleTestCase):
    def request(self, role=1):
        r = RequestFactory().get('/administracao/api/usuarios/test/metadados/')
        r.session = {'user_profile': {'role_id': role}}
        return r

    @patch.object(admin_views, '_auth_user_email', return_value='user@example.com')
    @patch.object(admin_views, '_get_table')
    def test_returns_email_and_recorded_authors(self, get, email):
        get.side_effect = lambda table, params: [{'created_at':'2026-09-05', 'details':{'actor':{'name':'Responsavel','user_id':'actor'}}}]
        response = admin_views.administration_user_metadata(self.request(), 'target')
        data = json.loads(response.content)
        self.assertEqual(data['email'], 'user@example.com')
        self.assertEqual(data['last_update']['name'], 'Responsavel')
        self.assertEqual(data['registration']['user_id'], 'actor')
        self.assertTrue(all(call.args[1]['limit'] == '1' for call in get.call_args_list))

    @patch.object(admin_views, '_auth_user_email', return_value=None)
    @patch.object(admin_views, '_get_table', return_value=[])
    def test_missing_history_does_not_invent_authorship(self, get, email):
        data = json.loads(admin_views.administration_user_metadata(self.request(), 'target').content)
        self.assertIsNone(data['registration'])
        self.assertIsNone(data['last_update'])

    @patch.object(admin_views, '_auth_user_email')
    def test_ordinary_user_cannot_read_email(self, email):
        self.assertEqual(admin_views.administration_user_metadata(self.request(4), 'target').status_code, 403)
        email.assert_not_called()

    @patch.object(admin_views, '_auth_user_email', return_value='user@example.com')
    @patch.object(admin_views, '_get_table')
    def test_legacy_registration_matches_email_and_creation_window(self, get, email):
        def query(table, params):
            if table == 'profiles':
                return [{'created_at': '2026-09-04T19:48:13+00:00'}]
            if 'details->>email' in params:
                self.assertEqual(params['details->>email'], 'eq.user@example.com')
                self.assertIn('created_at.gte.', params['and'])
                self.assertIn('created_at.lte.', params['and'])
                return [{'details': {'actor_name': 'Ricardo', 'actor_user_id': 'creator'}}]
            return []
        get.side_effect = query
        data = json.loads(admin_views.administration_user_metadata(self.request(), 'target').content)
        self.assertEqual(data['registration']['name'], 'Ricardo')
        self.assertEqual(data['registration']['user_id'], 'creator')

    @patch.object(admin_views, '_auth_user_email', return_value='user@example.com')
    @patch.object(admin_views, '_get_table')
    def test_ambiguous_legacy_events_are_not_attributed(self, get, email):
        def query(table, params):
            if table == 'profiles':
                return [{'created_at': '2026-09-04T19:48:13+00:00'}]
            if 'details->>email' in params:
                return [{'details': {'actor_name': 'One'}}, {'details': {'actor_name': 'Two'}}]
            return []
        get.side_effect = query
        data = json.loads(admin_views.administration_user_metadata(self.request(), 'target').content)
        self.assertIsNone(data['registration'])
