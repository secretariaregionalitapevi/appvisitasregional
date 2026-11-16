import json
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, RequestFactory, override_settings
from ColorAdminApp import admin_module_views, module_access
from ColorAdminApp.modules.access_control import user_scope, can_access
from ColorAdminApp.views import apiAuth


class DarpeApprovalTests(SimpleTestCase):
    def request(self, method='get', body=None, role=1):
        req = getattr(RequestFactory(), method)('/api/auth/?action=register',
            data=json.dumps(body or {}) if method != 'get' else {}, content_type='application/json')
        req.session = {'user_id': 'admin', 'user_profile': {'role_id': role, 'sector': 'D.A.R.P.E',
                       'comum': 'CENTRAL', 'municipio': 'ITAPEVI'}}
        return req

    @patch.object(module_access, 'explicit_modules', return_value=set())
    def test_darpe_scope_at_each_approved_level(self, _modules):
        for role, expected in [(4, 'local'), (3, 'municipal'), (2, 'regional')]:
            req = self.request(role=role)
            self.assertEqual(module_access.allowed_modules(req), {'darpe'})
            scope = user_scope(req)
            self.assertEqual(scope['level'], expected)
            self.assertTrue(can_access(scope, {'municipio': 'ITAPEVI', 'comum': 'CENTRAL'}))
            self.assertEqual(can_access(scope, {'municipio': 'ITAPEVI', 'comum': 'OUTRA'}), role != 4)
            self.assertEqual(can_access(scope, {'municipio': 'JANDIRA', 'comum': 'OUTRA'}), role == 2)

    @override_settings(SUPABASE_URL='https://example.test', SUPABASE_SERVICE_ROLE_KEY='test')
    @patch('ColorAdminApp.views.log_audit')
    @patch('ColorAdminApp.views.common_catalog', return_value=[{'comum': 'CENTRAL', 'cidade': 'ITAPEVI'}])
    @patch('ColorAdminApp.views.requests.post')
    def test_darpe_signup_is_pending_local_and_identified(self, post, _catalog, audit):
        post.side_effect = [Mock(status_code=200, ok=True, json=lambda: {'user': {'id': 'new-user'}}),
                            Mock(status_code=201, ok=True)]
        req = self.request('post', {'origem': 'darpe', 'comum': 'CENTRAL', 'email': 'teste@example.test',
                                   'password': 'example-password', 'full_name': 'Pessoa', 'role_id': 1,
                                   'setor': 'D.A.R.P.E'})
        response = apiAuth(req)
        self.assertEqual(response.status_code, 200)
        saved = post.call_args_list[1].kwargs['json']
        self.assertEqual(saved['sector'], 'D.A.R.P.E')
        self.assertEqual(saved['cadastro_origem'], 'app_darpe')
        self.assertEqual(saved['status'], 'pending')
        self.assertEqual(saved['role_id'], 4)
        self.assertNotIn('cadastro_origem_setor_selecionado', saved)
        self.assertEqual(post.call_args_list[0].kwargs['json']['data']['cadastro_origem_setor_selecionado'], 'D.A.R.P.E')
        self.assertEqual(audit.call_args.kwargs['details']['cadastro_origem'], 'app_darpe')

    @override_settings(SUPABASE_URL='https://example.test', SUPABASE_SERVICE_ROLE_KEY='test')
    @patch('ColorAdminApp.views.log_audit')
    @patch('ColorAdminApp.views.common_catalog', return_value=[{'comum':'CENTRAL','cidade':'ITAPEVI'}])
    @patch('ColorAdminApp.views.requests.post')
    def test_music_signup_uses_existing_profile_columns_and_remains_pending(self, post, _catalog, audit):
        def save(url, **kwargs):
            payload = kwargs['json']
            if '/auth/v1/signup' in url:
                return Mock(status_code=200, ok=True, json=lambda: {'user':{'id':'new-music-user'}})
            self.assertNotIn('cadastro_origem_setor_selecionado', payload)
            self.assertEqual(payload['sector'], 'Música')
            self.assertEqual(payload['cadastro_origem_setor_sugerido'], 'Música')
            self.assertEqual(payload['status'], 'pending')
            self.assertEqual(payload['role_id'], 4)
            return Mock(status_code=201, ok=True)
        post.side_effect = save
        response = apiAuth(self.request('post', {'comum':'CENTRAL','email':'music@example.test',
            'password':'example-password','full_name':'Pessoa','setor':'Música'}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_count, 2)
        audit.assert_called_once()

    @override_settings(SUPABASE_URL='https://example.test', SUPABASE_SERVICE_ROLE_KEY='test')
    @patch('ColorAdminApp.views.common_catalog', return_value=[{'comum': 'CENTRAL', 'cidade': 'ITAPEVI'}])
    @patch('ColorAdminApp.views.requests.post')
    def test_registration_rejects_departments_from_other_folders(self, post, _catalog):
        for setor in ('EBI', 'RJM', 'D.E.P.A.C'):
            req = self.request('post', {
                'comum': 'CENTRAL', 'email': 'teste@example.test',
                'password': 'example-password', 'full_name': 'Pessoa', 'setor': setor,
            })
            response = apiAuth(req)
            self.assertEqual(response.status_code, 400, setor)
        post.assert_not_called()

    @patch.object(admin_module_views, 'log_audit')
    @patch.object(admin_module_views, '_update_profile_via_rpc')
    @patch.object(admin_module_views, '_get_table')
    @patch.object(admin_module_views.requests, 'post')
    def test_global_can_grant_darpe_without_changing_primary_to_visits(self, post, get, update, audit):
        get.side_effect = [[{'user_id': 'target', 'sector': 'D.A.R.P.E'}], []]
        req = self.request('put', {'modules': ['darpe', 'visitas']})
        response = admin_module_views.administration_user_modules(req, 'target')
        self.assertEqual(response.status_code, 200)
        update.assert_called_once_with('target', {'sector': 'D.A.R.P.E'})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['json'][0]['module'], 'darpe')
        self.assertEqual(set(audit.call_args.args[3]['after']), {'darpe', 'visitas'})

    @patch.object(admin_module_views, 'log_audit')
    @patch.object(admin_module_views, '_update_profile_via_rpc')
    @patch.object(admin_module_views, '_get_table')
    @patch.object(admin_module_views.requests, 'post')
    def test_missing_gem_migration_does_not_change_sector_or_partially_save_grants(self, post, get, update, audit):
        import requests
        get.side_effect = [[{'user_id':'target','sector':'Música'}], [{'module':'musica','active':True}]]
        response = Mock(status_code=400)
        response.json.return_value = {'code':'23514','message':'violates check constraint user_module_access_module_check'}
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        post.return_value = response
        result = admin_module_views.administration_user_modules(
            self.request('put', {'modules':['musica','gem']}), 'target')
        self.assertEqual(result.status_code, 503)
        self.assertIn('050_gem_module_access.sql', json.loads(result.content)['error'])
        self.assertEqual(post.call_count, 1)
        self.assertEqual({row['module'] for row in post.call_args.kwargs['json']}, {'musica','gem'})
        update.assert_not_called()
        audit.assert_not_called()

    @patch.object(admin_module_views, '_get_table')
    def test_regional_cannot_grant_permissions(self, get):
        req = self.request('put', {'modules': ['darpe']}, role=2)
        req.path = '/administracao/api/usuarios/target/modulos/'
        self.assertEqual(admin_module_views.administration_user_modules(req, 'target').status_code, 403)
        get.assert_not_called()
