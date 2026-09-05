import json
from unittest.mock import patch

import requests
from django.test import RequestFactory, SimpleTestCase
from . import admin_views


class AdministrativeMutationTests(SimpleTestCase):
    user_id = '00000000-0000-0000-0000-000000000099'

    def response(self, status, payload):
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        return response

    def request(self, method, body=None, role=1):
        request = getattr(RequestFactory(), method)(
            '/administracao/api/usuarios/', data=json.dumps(body or {}), content_type='application/json')
        request.session = {'user_id': 'actor', 'user_profile': {'role_id': role}}
        return request

    @patch.object(admin_views.requests, 'patch')
    @patch.object(admin_views.requests, 'post')
    def test_legacy_claims_and_missing_rpc_use_backend_permissions(self, post, update):
        for status, error in [(403, {'code': '42501', 'message': 'Service role required'}),
                              (404, {'code': 'PGRST202'})]:
            with self.subTest(status=status):
                post.return_value = self.response(status, error)
                update.return_value = self.response(200, [{'user_id': self.user_id, 'full_name': 'Nome'}])
                result = admin_views._update_profile_via_rpc(self.user_id, {'full_name': ' Nome '})
                self.assertEqual(result['full_name'], 'Nome')
                self.assertEqual(update.call_args.kwargs['params'], {'user_id': f'eq.{self.user_id}'})
                self.assertEqual(update.call_args.kwargs['json'], {'full_name': 'Nome'})
                self.assertEqual(update.call_args.kwargs['headers'], admin_views._headers('return=representation'))

    @patch.object(admin_views.requests, 'patch')
    @patch.object(admin_views.requests, 'post')
    def test_other_rpc_failures_never_trigger_second_write(self, post, update):
        for status, error in [(403, {'code': '42501', 'message': 'permission denied'}),
                              (400, {'code': '22023'}), (500, {}), (404, {})]:
            post.return_value = self.response(status, error)
            with self.assertRaises(requests.HTTPError):
                admin_views._update_profile_via_rpc(self.user_id, {'status': 'approved'})
        update.assert_not_called()

    @patch.object(admin_views.requests, 'patch')
    def test_direct_update_requires_matching_returned_profile(self, update):
        for rows in [[], [{'user_id': 'another-user'}]]:
            update.return_value = self.response(200, rows)
            with self.assertRaises(requests.RequestException):
                admin_views._update_profile_direct(self.user_id, {'status': 'rejected'})

    @patch.object(admin_views, '_update_profile_via_rpc')
    @patch.object(admin_views, '_get_table')
    @patch.object(admin_views.requests, 'delete')
    @patch.object(admin_views, 'log_audit')
    def test_delete_revokes_through_shared_helper(self, audit, delete, get, update):
        get.return_value = [{'user_id': self.user_id}]
        delete.return_value = self.response(204, None)
        response = admin_views.administration_user(self.request('delete'), self.user_id)
        self.assertEqual(response.status_code, 200)
        update.assert_called_once_with(self.user_id, {'status': 'rejected'})
        self.assertEqual(delete.call_count, 2)

    @patch.object(admin_views, '_update_profile_via_rpc', side_effect=requests.RequestException())
    @patch.object(admin_views, '_get_table')
    @patch.object(admin_views.requests, 'delete')
    def test_delete_stops_when_revocation_fails(self, delete, get, update):
        get.return_value = [{'user_id': self.user_id}]
        self.assertEqual(admin_views.administration_user(self.request('delete'), self.user_id).status_code, 502)
        delete.assert_not_called()

    @patch.object(admin_views, '_get_table')
    def test_ordinary_user_cannot_mutate_profiles(self, get):
        for method in ['patch', 'delete']:
            self.assertEqual(admin_views.administration_user(self.request(method, role=4), self.user_id).status_code, 403)
        get.assert_not_called()

    @patch.object(admin_views, 'log_audit')
    @patch.object(admin_views.requests, 'patch')
    @patch.object(admin_views, '_get_table')
    def test_partial_ministry_edit_normalizes_blank_dates(self, get, update, audit):
        get.return_value = [{'id': self.user_id, 'nome': 'Teste', 'ministerio': 'Teste', 'comum': 'Teste', 'municipio': 'Teste'}]
        update.return_value = self.response(200, get.return_value)
        response = admin_views.operational_record(self.request('patch', {'data_apresentacao': '', 'data_ordenacao': ' '}), 'ministerio', self.user_id)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(update.call_args.kwargs['json']['data_apresentacao'])
        self.assertIsNone(update.call_args.kwargs['json']['data_ordenacao'])

    @patch.object(admin_views, 'log_audit')
    @patch.object(admin_views.requests, 'patch')
    @patch.object(admin_views, '_get_table')
    def test_santa_ceia_optional_year_and_invalid_inputs(self, get, update, audit):
        get.return_value = [{'id': self.user_id, 'data_evento': '2026-09-04', 'comum': 'Teste', 'municipio': 'Teste'}]
        update.return_value = self.response(200, get.return_value)
        for value, expected in [('', None), ('2025', 2025)]:
            response = admin_views.operational_record(self.request('patch', {'ano_anterior': value}), 'santa-ceia', self.user_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(update.call_args.kwargs['json']['ano_anterior'], expected)
        update.reset_mock()
        for body in [{'ano_anterior': 'abc'}, {'data_evento': '2026-02-30'}]:
            self.assertEqual(admin_views.operational_record(self.request('patch', body), 'santa-ceia', self.user_id).status_code, 400)
        update.assert_not_called()
