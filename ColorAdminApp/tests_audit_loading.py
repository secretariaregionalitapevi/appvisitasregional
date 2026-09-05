import json
import threading
from unittest.mock import patch
import requests
from django.test import RequestFactory, SimpleTestCase
from .admin_views import administration_data


class AuditDataLoadingTests(SimpleTestCase):
    def request(self, role=1):
        request = RequestFactory().get('/administracao/api/dados/')
        request.session = {'user_profile': {'role_id': role}}
        return request

    @patch('ColorAdminApp.admin_views._get_table')
    def test_independent_queries_start_together_and_deduplicate(self, get):
        barrier = threading.Barrier(5, timeout=3)
        def query(table, params):
            barrier.wait()
            return [{'user_id': 'same'}, {'user_id': 'same'}] if table == 'profiles' else []
        get.side_effect = query
        response = administration_data(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(json.loads(response.content)['profiles']), 1)
        self.assertEqual(get.call_count, 5)

    @patch('ColorAdminApp.admin_views._get_table')
    def test_optional_modules_can_be_missing(self, get):
        def query(table, params):
            if table == 'user_module_access':
                raise requests.RequestException()
            return []
        get.side_effect = query
        response = administration_data(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['module_access'], [])

    @patch('ColorAdminApp.admin_views._get_table', side_effect=requests.RequestException())
    def test_required_query_failure_is_reported(self, get):
        self.assertEqual(administration_data(self.request()).status_code, 502)

    @patch('ColorAdminApp.admin_views._get_table')
    def test_non_global_cannot_start_queries(self, get):
        self.assertEqual(administration_data(self.request(role=4)).status_code, 403)
        get.assert_not_called()
