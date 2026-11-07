import copy
import json
import requests
from unittest.mock import Mock, patch
from uuid import uuid4
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.template.loader import render_to_string
from ColorAdminApp.modules import darpe_atendimentos as att
from ColorAdminApp.tests.tests_darpe import request_for


class AttendanceTests(SimpleTestCase):
    def setUp(self):
        self.req = request_for('/darpe/atendimentos/api/atendimentos/')
        self.person = {'id': str(uuid4()), 'nome_completo': 'Atendente DARPE', 'status': 'ATIVO',
                       'darpe_atendente': True, 'cidade': 'ITAPEVI', 'comum_congregacao': 'CENTRAL'}
        self.payload = {'id': str(uuid4()), 'data': '2026-01-01', 'hora_inicio': '09:30', 'hora_fim': '11:00',
                        'setor': 2, 'local': 'Unidade de atendimento', 'municipio': 'ITAPEVI', 'comum': 'CENTRAL',
                        'hinos': [374, 7], 'pedidos_oracao': {'familias': 'todas'},
                        'equipe': [{'cadastro_id': self.person['id'], 'funcao': 'atendente'}]}
        self.mock_people = patch.object(att, 'people', return_value=[self.person])
        self.mock_people.start()
        self.addCleanup(self.mock_people.stop)

    def test_papeleta_and_all_families(self):
        result = att.validate(self.payload, self.req)
        self.assertEqual(result['pedidos_oracao']['familias'], 'todas')
        self.assertEqual(result['equipe'][0]['nome'], self.person['nome_completo'])
        self.assertEqual(result['pedidos_oracao']['viagens'], 0)

    def test_disallowed_person_role_inactive_and_duplicates(self):
        for change in ('foreign', 'musico', 'inactive', 'duplicate', 'no_responsible'):
            payload = copy.deepcopy(self.payload)
            self.person['status'] = 'ATIVO'
            if change == 'foreign': payload['equipe'][0]['cadastro_id'] = str(uuid4())
            if change == 'musico': payload['equipe'][0]['funcao'] = 'musico'
            if change == 'inactive': self.person['status'] = 'INATIVO'
            if change == 'duplicate': payload['equipe'] *= 2
            if change == 'no_responsible': payload['equipe'] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                att.validate(payload, self.req)

    def test_invalid_dates_times_sector_prayers_hymns(self):
        for key, value in [('data','2026-02-30'),('data','2099-01-01'),('hora_fim','08:00'),
                           ('hora_inicio','invalid'),('setor',5),('setor',True),('hinos',[481]),
                           ('hinos',[True]),('pedidos_oracao',{'causas':'todas'}),
                           ('pedidos_oracao',{'viagens':-1}),('pedidos_oracao',{'viagens':1.5})]:
            payload = {**self.payload, key:value}
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                att.validate(payload, self.req)

    def test_municipal_scope_cannot_be_forged(self):
        self.req.session['user_profile'].update(access_level='municipal', municipio='JANDIRA')
        with self.assertRaises(PermissionError):
            att.validate(self.payload, self.req)

    def test_homonymous_common_in_another_city_is_not_local_scope(self):
        scope = {'level':'local','municipio':'ITAPEVI','comum':'CENTRAL'}
        self.assertFalse(att.in_scope(scope,{'municipio':'JANDIRA','comum':'CENTRAL'}))
        self.assertTrue(att.in_scope(scope,{'municipio':'ITAPEVI','comum':'CENTRAL'}))

    @patch.object(att, 'rows')
    def test_listing_applies_scope(self, rows):
        rows.return_value = [{**self.payload, 'created_at':'2026-01-01T12:00:00Z'},
                             {**self.payload, 'municipio':'JANDIRA'}]
        self.req.session['user_profile'].update(access_level='municipal', municipio='ITAPEVI')
        response = att.api(self.req)
        self.assertEqual(len(json.loads(response.content)['items']), 1)

    def test_search_only_returns_allowed_fields_and_role(self):
        self.person.update(cpf='00000000000',telefone='11999999999')
        req = request_for('/darpe/atendimentos/api/pessoas/?funcao=atendente&q=Atendente')
        data = json.loads(att.api(req, 'pessoas').content)['items']
        self.assertEqual(len(data), 1)
        self.assertNotIn('cpf', data[0]); self.assertNotIn('telefone', data[0])
        req = request_for('/darpe/atendimentos/api/pessoas/?funcao=musico&q=Atendente')
        self.assertEqual(json.loads(att.api(req, 'pessoas').content)['items'], [])

    @patch.object(att.requests, 'post')
    def test_create_atomic_papeleta_with_actor(self, post):
        post.return_value = Mock(status_code=201, json=lambda:[self.payload])
        req = request_for('/darpe/atendimentos/api/atendimentos/', 'post', self.payload)
        self.assertEqual(att.api(req).status_code, 201)
        saved = post.call_args.kwargs['json']
        self.assertTrue(post.call_args.args[0].endswith('/rest/v1/darpe_papeletas'))
        self.assertEqual(saved['created_by'], 'user-1')
        self.assertEqual(saved['equipe'][0]['nome'], self.person['nome_completo'])

    @patch.object(att, 'rows')
    def test_missing_papeleta_schema_returns_actionable_error(self, rows):
        response=Mock(json=lambda:{'code':'PGRST205'})
        rows.side_effect=requests.HTTPError(response=response)
        result=att.api(self.req)
        self.assertEqual(result.status_code,503)
        body=json.loads(result.content)
        self.assertEqual(body['code'],'darpe_schema_missing')
        self.assertIn('atualização',body['error'])

    @patch.object(att, 'rows')
    @patch.object(att.requests, 'post')
    def test_duplicate_retry_does_not_insert_again(self, post, rows):
        post.return_value = Mock(status_code=409)
        rows.return_value = [{**self.payload,'created_by':'user-1'}]
        req = request_for('/darpe/atendimentos/api/atendimentos/','post',self.payload)
        self.assertEqual(att.api(req).status_code, 200)

    @patch.object(att, 'rows')
    def test_cookie_session_cannot_authenticate_mobile(self, rows):
        self.assertEqual(att.mobile_api(self.req,'contexto').status_code,401)
        rows.assert_not_called()

    @override_settings(SUPABASE_ANON_KEY='anon')
    @patch.object(att, 'read_profile')
    @patch.object(att.requests, 'get')
    def test_mobile_rechecks_approval_and_module(self, get, rows):
        req = RequestFactory().get('/darpe/mobile/api/contexto/',HTTP_AUTHORIZATION='Bearer token')
        get.return_value = Mock(ok=True,json=lambda:{'id':str(uuid4())})
        rows.return_value = [{'status':'pending','sector':'darpe'}]
        self.assertEqual(att.mobile_api(req,'contexto').status_code,403)
        rows.return_value = [{'status':'approved','sector':'Musica','role_id':3}]
        with patch('ColorAdminApp.modules.module_access.explicit_modules',return_value=set()):
            self.assertEqual(att.mobile_api(req,'contexto').status_code,403)
        rows.return_value = [{'status':'approved','sector':'darpe','role_id':2}]
        with patch('ColorAdminApp.modules.module_access.explicit_modules',return_value=set()), patch.object(att,'common_catalog',return_value=[]):
            self.assertEqual(att.mobile_api(req,'contexto').status_code,200)

    @patch.object(att.requests, 'get')
    def test_profile_lookup_uses_user_id_without_nonexistent_id_order(self, get):
        get.return_value = Mock(json=lambda:[{'user_id':'account','status':'approved'}])
        self.assertEqual(att.read_profile('account')[0]['status'],'approved')
        params = get.call_args.kwargs['params']
        self.assertEqual(params['user_id'],'eq.account')
        self.assertNotIn('order',params)

    def test_template_contains_papeleta_and_cancel(self):
        html=render_to_string('partial/darpe-atendimentos.html')
        for label in ['Atendimentos','Pedidos de oração','Atendente responsável','app-btn-cancel','fa-xmark']:
            self.assertIn(label,html)
