import json
from unittest.mock import patch
from uuid import uuid4

import requests
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from ColorAdminApp.modules import darpe_atendimentos as att


@override_settings(SUPABASE_URL='https://db.example', SUPABASE_ANON_KEY='test', SUPABASE_SERVICE_ROLE_KEY='test')
class DarpeMobileAuditTests(SimpleTestCase):
    def setUp(self):
        self.user_id = str(uuid4())
        self.profile = {'user_id': self.user_id, 'status': 'approved', 'full_name': 'Pessoa real', 'role_id': 2}

    def request(self, action):
        return RequestFactory().post(
            '/darpe/mobile/api/' + action + '/',
            data=json.dumps({'user_id': str(uuid4())}), content_type='application/json',
            HTTP_AUTHORIZATION='Bearer test-token',
        )

    @patch.object(att, 'can_access_module', return_value=True)
    @patch.object(att, 'read_profile')
    @patch.object(att.requests, 'post')
    @patch.object(att.requests, 'get')
    def test_login_audit_uses_verified_user(self, get, post, profiles, _access):
        get.return_value.ok = True
        get.return_value.json.return_value = {'id': self.user_id}
        profiles.return_value = [self.profile]

        response = att.mobile_api(self.request('audit-login'), 'audit-login')

        self.assertEqual(response.status_code, 201)
        event = post.call_args.kwargs['json']
        self.assertEqual(event['user_id'], self.user_id)
        self.assertEqual(event['details']['actor']['name'], 'Pessoa real')
        self.assertEqual(event['details']['source'], 'APP_DARPE')

    @patch.object(att, 'audit_mobile')
    @patch.object(att, 'can_access_module', return_value=False)
    @patch.object(att, 'read_profile')
    @patch.object(att.requests, 'get')
    def test_denied_login_is_not_recorded_as_success(self, get, profiles, _access, audit):
        get.return_value.ok = True
        get.return_value.json.return_value = {'id': self.user_id}
        profiles.return_value = [self.profile]
        self.assertEqual(att.mobile_api(self.request('audit-login'), 'audit-login').status_code, 403)
        audit.assert_not_called()

    @patch.object(att, 'audit_mobile')
    @patch.object(att, 'api')
    @patch.object(att, 'read_profile')
    @patch.object(att.requests, 'get')
    def test_successful_save_is_audited_and_failure_is_explicit(self, get, profiles, api, audit):
        get.return_value.ok = True
        get.return_value.json.return_value = {'id': self.user_id}
        profiles.return_value = [self.profile]
        api.return_value = JsonResponse({'item': {'id': 'record-id'}}, status=201)
        response = att.mobile_api(self.request('atendimentos'), 'atendimentos')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(audit.call_args.args[1:], ('CREATE', {'entity': 'darpe_papeletas', 'entity_id': 'record-id'}))
        audit.side_effect = requests.RequestException('audit unavailable')
        response = att.mobile_api(self.request('atendimentos'), 'atendimentos')
        self.assertEqual(response.status_code, 503)
        self.assertIn('foi salvo', json.loads(response.content)['error'])

    @patch.object(att, 'audit_mobile')
    @patch.object(att, 'api')
    @patch.object(att, 'read_profile')
    @patch.object(att.requests, 'get')
    def test_failed_save_is_not_audited_as_success(self, get, profiles, api, audit):
        get.return_value.ok = True
        get.return_value.json.return_value = {'id': self.user_id}
        profiles.return_value = [self.profile]
        api.return_value = JsonResponse({'error': 'Inválido'}, status=400)
        response = att.mobile_api(self.request('atendimentos'), 'atendimentos')
        self.assertEqual(response.status_code, 400)
        audit.assert_not_called()

    @patch.object(att, 'audit_mobile')
    @patch.object(att, 'api')
    @patch.object(att, 'read_profile')
    @patch.object(att.requests, 'get')
    def test_idempotent_retry_does_not_duplicate_creation_event(self, get, profiles, api, audit):
        get.return_value.ok = True
        get.return_value.json.return_value = {'id': self.user_id}
        profiles.return_value = [self.profile]
        api.return_value = JsonResponse({'item': {'id': 'record-id'}, 'message': 'Atendimento já registrado.'})
        response = att.mobile_api(self.request('atendimentos'), 'atendimentos')
        self.assertEqual(response.status_code, 200)
        audit.assert_not_called()

    @patch.object(att, 'audit_mobile')
    @patch.object(att, 'api')
    @patch.object(att, 'read_profile')
    @patch.object(att.requests, 'get')
    def test_edit_records_update(self, get, profiles, api, audit):
        get.return_value.ok = True
        get.return_value.json.return_value = {'id': self.user_id}
        profiles.return_value = [self.profile]
        api.return_value = JsonResponse({'item': {'id': 'record-id'}})
        request = RequestFactory().patch(
            '/darpe/mobile/api/atendimentos/', data='{}', content_type='application/json',
            HTTP_AUTHORIZATION='Bearer ' + 'test-token',
        )
        self.assertEqual(att.mobile_api(request, 'atendimentos').status_code, 200)
        self.assertEqual(audit.call_args.args[1], 'UPDATE')
