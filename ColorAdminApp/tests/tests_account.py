import io
import json
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.test import RequestFactory, SimpleTestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from ColorAdminApp.modules import account_views


class AccountTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.identity = str(uuid4())
        self.session = {'authenticated': True, 'user_id': self.identity,
                        'user_profile': {'full_name': 'Ricardo Grangeiro', 'role_id': 1,
                                         'status': 'approved', 'email': 'teste@example.test'}}

    def request(self, **data):
        request = self.factory.post('/extra/profile', data)
        request.session = self.session
        return request

    @patch.object(account_views.requests, 'get')
    def test_postcode_lookup_returns_street_and_handles_missing_and_failure(self, read):
        from django.core.cache import cache
        cache.delete('account-cep:06700241')
        self.addCleanup(cache.delete, 'account-cep:06700241')
        request = self.factory.get('/extra/profile/cep', {'cep': '06700-241'})
        request.session = self.session
        address = {'cep': '06700-241', 'logradouro': 'Rua Coapa', 'bairro': 'Jardim Leonor', 'localidade': 'Cotia', 'uf': 'SP'}
        read.return_value = Mock(json=Mock(return_value=address))
        result = account_views.postcode(request)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(result.content), address)
        self.assertEqual(read.call_args.args[0], 'https://viacep.com.br/ws/06700241/json/')
        cache.delete('account-cep:06700241')
        read.return_value.json.return_value = {'erro': True}
        self.assertEqual(account_views.postcode(request).status_code, 404)
        read.side_effect = requests.Timeout()
        self.assertEqual(account_views.postcode(request).status_code, 503)
        request.session = {}
        self.assertEqual(account_views.postcode(request).status_code, 401)

    def test_account_pages_render_real_profile_and_settings(self):
        for path, view, title in [('/extra/profile', account_views.profile, 'Meu perfil'),
                                  ('/extra/settings', account_views.account_settings, 'Configurações')]:
            request = self.factory.get(path)
            request.session = self.session
            response = view(request)
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertIn(title, html)
            self.assertIn('Ricardo Grangeiro', html)
            self.assertNotIn('Sean Ngu', html)
            self.assertNotIn('Lorem ipsum', html)
            self.assertIn('fa-right-from-bracket', html)
            self.assertIn('fa-user-pen', html)

    @patch('ColorAdminApp.views.log_audit')
    @patch.object(account_views.requests, 'patch')
    def test_save_only_changes_own_name_and_updates_pdf_identity(self, update, audit):
        name = 'Ricardo C. Grangeiro'
        update.return_value = Mock(json=Mock(return_value=[{'user_id': self.identity, 'full_name': name}]))
        request = self.request(full_name='  Ricardo C.  Grangeiro ', user_id=str(uuid4()), role_id='1', status='approved', sector='Global')
        response = account_views.profile(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['saved'])
        self.assertEqual(update.call_args.kwargs['json'], {'full_name': name})
        self.assertEqual(update.call_args.kwargs['params']['user_id'], 'eq.' + self.identity)
        self.assertEqual(request.session['user_profile']['full_name'], name)
        self.assertEqual(request.session['user_profile']['role_id'], 1)
        audit.assert_called_once()
        # Generate a real PDF through the existing report path with the updated session.
        from pypdf import PdfReader
        from .tests_regional_routes import members, teams, DAY, COMMONS
        from ColorAdminApp.modules.regional_routes import build_plan, finalize_plan
        from ColorAdminApp.modules.regional_route_reports import build_group_pdf, prepare_navigation
        plan = finalize_plan(build_plan(members(1), [], teams(1), DAY, 'ITAPEVI', COMMONS))
        group = dict(plan['groups'][0], houses=plan['houses'])
        prepare_navigation([group], 'ITAPEVI', request)
        pdf = build_group_pdf(plan, group, request, include_map=False)
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn('Impresso por:', text)
        self.assertIn(name, text)
        self.assertIn('CONGREGAÇÃO CRISTÃ NO BRASIL', text)

    @patch.object(account_views.requests, 'patch')
    def test_invalid_or_unauthenticated_request_never_writes(self, update):
        for name in ('', 'X', 'A' * 181):
            self.assertEqual(account_views.profile(self.request(full_name=name)).status_code, 400)
        request = self.request(full_name='Outro nome')
        request.session = {}
        self.assertEqual(account_views.profile(request).status_code, 302)
        request = self.factory.get('/extra/settings')
        request.session = {}
        self.assertEqual(account_views.account_settings(request).status_code, 302)
        update.assert_not_called()

    @patch('ColorAdminApp.views.log_audit')
    @patch.object(account_views.requests, 'patch')
    def test_failed_or_unconfirmed_write_keeps_session_unchanged(self, update, audit):
        for result in ([], [{'user_id': str(uuid4()), 'full_name': 'Novo nome'}],
                       [{'user_id': self.identity, 'full_name': 'Nome anterior'}]):
            update.return_value = Mock(json=Mock(return_value=result))
            self.assertEqual(account_views.profile(self.request(full_name='Novo nome')).status_code, 503)
        update.side_effect = requests.Timeout()
        self.assertEqual(account_views.profile(self.request(full_name='Novo nome')).status_code, 503)
        self.assertEqual(self.session['user_profile']['full_name'], 'Ricardo Grangeiro')
        audit.assert_not_called()

    @patch('ColorAdminApp.middleware.supabase_get')
    def test_other_active_sessions_receive_saved_name_on_next_request(self, read):
        from django.http import HttpResponse
        from ColorAdminApp.middleware import SupabaseAuthMiddleware
        name = 'Ricardo C. Grangeiro'
        read.return_value = Mock(json=Mock(return_value=[{
            'user_id': self.identity, 'status': 'approved', 'role_id': 1, 'full_name': name,
        }]))
        request = self.factory.get('/visitas/api/dashboard/')
        request.session = self.session
        response = SupabaseAuthMiddleware(lambda req: HttpResponse(req.session['user_profile']['full_name']))(request)
        self.assertEqual(response.content.decode(), name)
        self.assertIn('full_name', read.call_args.kwargs['params']['select'])

    @patch('ColorAdminApp.views.log_audit')
    @patch.object(account_views.requests, 'patch')
    def test_contacts_address_and_photo_save_without_permission_changes(self, update, audit):
        from PIL import Image
        picture = io.BytesIO()
        Image.new('RGB', (600, 400), '#1e4b7a').save(picture, 'PNG')
        update.side_effect = lambda *args, **kwargs: Mock(json=Mock(return_value=[{'user_id': self.identity, **kwargs['json']}]))
        photo = SimpleUploadedFile('photo.png', picture.getvalue(), content_type='image/png')
        request = self.request(full_name='Ricardo C. Grangeiro', celular='(11) 99999-9999',
                               cep='06600-000', bairro='Centro', avatar=photo, role_id=1, comum='OUTRA')
        response = account_views.profile(request)
        self.assertEqual(response.status_code, 200)
        saved = update.call_args.kwargs['json']
        self.assertEqual(saved['bairro'], 'Centro')
        self.assertNotIn('role_id', saved)
        self.assertNotIn('comum', saved)
        self.assertTrue(saved['avatar_url'].startswith('data:image/jpeg;base64,'))
        self.assertTrue(request.session['user_profile']['avatar_url'].startswith('/extra/profile/avatar?v='))
        self.assertLess(len(request.session['user_profile']['avatar_url']), 100)

    @patch('ColorAdminApp.views.log_audit')
    @patch.object(account_views.requests, 'patch')
    def test_photo_removal_is_persisted(self, update, audit):
        update.side_effect = lambda *args, **kwargs: Mock(json=Mock(return_value=[{'user_id': self.identity, **kwargs['json']}]))
        response = account_views.profile(self.request(full_name='Ricardo Grangeiro', remove_avatar='1'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(update.call_args.kwargs['json']['avatar_url'])
        self.assertIsNone(self.session['user_profile']['avatar_url'])

    @patch('ColorAdminApp.views.log_audit')
    @patch.object(account_views.requests, 'patch')
    def test_postcode_mask_and_separate_number_roundtrip(self, update, audit):
        update.side_effect = lambda *args, **kwargs: Mock(json=Mock(return_value=[{'user_id': self.identity, **kwargs['json']}]))
        request = self.request(full_name='Ricardo Grangeiro', cep='06700241', logradouro='Rua de Teste', numero='123 A')
        self.assertEqual(account_views.profile(request).status_code, 200)
        self.assertEqual(update.call_args.kwargs['json']['cep'], '06700-241')
        self.assertEqual(update.call_args.kwargs['json']['logradouro_numero'], 'Rua de Teste, 123 A')
        context = account_views.account_context(request)
        self.assertEqual(context['account_street'], 'Rua de Teste')
        self.assertEqual(context['account_number'], '123 A')

    @patch.object(account_views.requests, 'patch')
    def test_invalid_contacts_and_photo_never_reach_database(self, update):
        for options in ({'cep': '123'}, {'celular': '12345'}, {'bairro': 'X' * 121},
                        {'avatar': SimpleUploadedFile('photo.jpg', b'not an image', content_type='image/jpeg')}):
            response = account_views.profile(self.request(full_name='Ricardo Grangeiro', **options))
            self.assertEqual(response.status_code, 400)
        update.assert_not_called()

    @patch.object(account_views.requests, 'get')
    def test_photo_endpoint_reads_only_authenticated_owners_image(self, read):
        import base64
        image = b'jpeg-test-content'
        read.return_value = Mock(json=Mock(return_value=[{'avatar_url': 'data:image/jpeg;base64,' + base64.b64encode(image).decode()}]))
        request = self.factory.get('/extra/profile/avatar')
        request.session = self.session
        response = account_views.avatar(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, image)
        self.assertEqual(read.call_args.kwargs['params']['user_id'], 'eq.' + self.identity)
        request.session = {}
        self.assertEqual(account_views.avatar(request).status_code, 401)
