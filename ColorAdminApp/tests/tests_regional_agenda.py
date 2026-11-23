import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from ColorAdminApp.modules import regional_agenda as agenda


@override_settings(SUPABASE_URL='https://db.example', SUPABASE_SERVICE_ROLE_KEY='test', AGENDA_N8N_TOKEN='worker-secret')
class RegionalAgendaTests(SimpleTestCase):
    def setUp(self):
        self.user_id = str(uuid4())
        self.event_id = str(uuid4())
        self.google_patch=patch.object(agenda,'google_window',return_value=([],{'instalada':True,'pending':0,'leituras':[]}))
        self.google_patch.start();self.addCleanup(self.google_patch.stop)

    def request(self, path='/musica/agenda-regional/api/eventos/', payload=None, method='get', token=None):
        req = getattr(RequestFactory(), method)(path, data=json.dumps(payload or {}) if method == 'post' else {},
                                               content_type='application/json', **({'HTTP_AUTHORIZATION': token} if token else {}))
        req.session = {'authenticated': True, 'user_id': self.user_id,
                       'user_profile': {'role_id': 1, 'full_name': 'Responsável', 'sector': 'Administrativo'}}
        return req

    def payload(self):
        start = datetime.now(timezone.utc) + timedelta(days=2)
        return {'id': self.event_id, 'administracao_id': 'itapevi', 'municipio': 'Itapevi',
                'titulo': 'Reunião', 'categoria': 'Reunião Técnica', 'local': 'Central',
                'inicio': start.isoformat(), 'fim': (start + timedelta(hours=2)).isoformat()}

    @patch.object(agenda, 'operate')
    def test_anonymous_cannot_create(self, operate):
        req = self.request(payload=self.payload(), method='post'); req.session = {}
        self.assertEqual(agenda.events_api(req).status_code, 403)
        operate.assert_not_called()

    @patch.object(agenda, 'can_access_module', return_value=False)
    @patch.object(agenda, 'operate')
    def test_other_folder_cannot_create(self, operate, _access):
        self.assertEqual(agenda.events_api(self.request(payload=self.payload(), method='post')).status_code, 403)
        operate.assert_not_called()

    @patch.object(agenda, 'operate', return_value={'id': 'event', 'status': 'PENDENTE_ADM', 'lease_token': 'private'})
    def test_actor_and_status_cannot_be_forged(self, operate):
        data = {**self.payload(), 'p_actor': str(uuid4()), 'p_master': False, 'status': 'CONFIRMADO'}
        response = agenda.events_api(self.request(payload=data, method='post'))
        self.assertEqual(response.status_code, 201)
        _, payload, actor = operate.call_args.args
        self.assertNotIn('status', payload)
        self.assertEqual(actor['p_actor'], self.user_id)
        self.assertNotIn('lease_token', json.loads(response.content)['event'])

    @patch.object(agenda, 'operate')
    def test_bad_interval_and_missing_timezone_never_reach_database(self, operate):
        for changes in ({'fim': self.payload()['inicio']}, {'inicio': '2026-12-01T19:00:00'}, {'titulo': ''}):
            response = agenda.events_api(self.request(payload={**self.payload(), **changes}, method='post'))
            self.assertEqual(response.status_code, 400)
        operate.assert_not_called()

    @patch.object(agenda, 'read', return_value=[])
    def test_regular_regional_user_cannot_assign_himself(self, read):
        req = self.request(); req.session['user_profile']['role_id'] = 2
        self.assertEqual(agenda.configuration_api(req).status_code, 403)
        read.assert_not_called()

    @patch.object(agenda, 'roles', return_value=[])
    @patch.object(agenda, 'read')
    def test_outside_municipality_only_sees_busy_interval(self, read, _roles):
        req = self.request(); req.session['user_profile'].update(role_id=3, municipio='Itapevi')
        read.side_effect = [[{'id':'itapevi','nome':'Itapevi','municipios':['Itapevi'],'calendar_id':'calendar','prazo_horas':48}],
                            [{**c,'calendar_id':'cal-'+c['id']} for c in agenda.CALENDAR_BY_ID.values()],
                            [{'id':self.event_id,'administracao_id':'cotia','agenda_id':'cotia','municipio':'Cotia','inicio':'2026-12-01T19:00:00-03:00',
                              'fim':'2026-12-01T21:00:00-03:00','status':'CONFIRMADO','titulo':'Privado','local':'Sigiloso',
                              'criado_por':str(uuid4()),'conflitos':[]}]]
        with patch.object(agenda, 'can_access_module', return_value=True):
            response = agenda.events_api(req)
        row = json.loads(response.content)['events'][0]
        self.assertEqual(row['titulo'], 'Horário reservado')
        self.assertNotIn('local', row)
        self.assertNotIn('criado_por', row)

    def test_affected_delegate_can_review_cross_administration_request(self):
        who = {'p_nivel':'municipal','p_actor':self.user_id,'p_municipio':'Itapevi'}
        event = {'criado_por':str(uuid4()),'administracao_id':'cotia','municipio':'Cotia','conflitos':['existing']}
        self.assertTrue(agenda.can_view(event, who, [{'papel':'ENCARREGADO','administracao_id':'itapevi'}],
                                       [{'id':'existing','administracao_id':'itapevi'}]))
        self.assertFalse(agenda.can_view(event, who, [], []))

    def test_local_user_does_not_inherit_municipal_read_scope(self):
        who = {'p_nivel':'local','p_actor':self.user_id,'p_municipio':'Itapevi'}
        self.assertFalse(agenda.can_view({'criado_por':str(uuid4()),'administracao_id':'itapevi',
            'municipio':'Itapevi','conflitos':[]}, who, [], []))

    @patch.object(agenda, 'can_access_module', return_value=True)
    @patch.object(agenda, 'roles', return_value=[{'papel':'ENCARREGADO','administracao_id':'itapevi'}])
    @patch.object(agenda, 'read')
    def test_pending_list_includes_cross_request_when_source_is_already_confirmed(self, read, _roles, _access):
        req=self.request();req.GET=req.GET.copy();req.GET['pending']='1'
        req.session['user_profile'].update(role_id=3,municipio='Itapevi')
        event={'id':self.event_id,'criado_por':str(uuid4()),'administracao_id':'cotia','municipio':'Cotia',
               'titulo':'Solicitação de Cotia','conflitos':['source'],'status':'PENDENTE_ADM'}
        read.side_effect=[[{'id':'cotia','nome':'Cotia','municipios':['Cotia'],'calendar_id':'cal','prazo_horas':48}],
                          [{**c,'calendar_id':'cal-'+c['id']} for c in agenda.CALENDAR_BY_ID.values()],
                          [event],[{'id':'source','administracao_id':'itapevi'}]]
        response=agenda.events_api(req)
        self.assertTrue(json.loads(response.content)['events'][0]['detalhes'])

    @patch.object(agenda, 'rpc')
    def test_worker_requires_token_even_with_logged_in_master(self, rpc):
        for token in (None, 'Bearer wrong', 'worker-secret'):
            response = agenda.integration_api(self.request(method='post', token=token), 'buscar')
            self.assertEqual(response.status_code, 401)
        rpc.assert_not_called()

    @override_settings(AGENDA_N8N_TOKEN='')
    @patch.object(agenda, 'rpc')
    def test_empty_configured_secret_fails_closed(self, rpc):
        self.assertEqual(agenda.integration_api(self.request(method='post', token='Bearer '), 'buscar').status_code, 401)
        rpc.assert_not_called()

    @patch.object(agenda, 'rpc', return_value={'job':None})
    def test_worker_works_without_user_session(self, rpc):
        req = self.request(method='post', token='Bearer worker-secret',payload={'protocol_version':2});req.session={}
        self.assertEqual(agenda.integration_api(req, 'buscar').status_code, 200)
        rpc.assert_called_once_with('agenda_trabalho', {'p_acao':'buscar','p_dados':{'protocol_version':2}})

    @patch.object(agenda, 'rpc')
    def test_wrong_google_identifier_is_rejected(self, rpc):
        req = self.request(method='post', token='Bearer worker-secret', payload={
            'id':self.event_id,'lease_token':str(uuid4()),'resultado':'confirmado','google_event_id':'wrong','protocol_version':2})
        self.assertEqual(agenda.integration_api(req, 'resultado').status_code, 400)
        rpc.assert_not_called()

    @patch('ColorAdminApp.middleware.supabase_get')
    def test_machine_endpoint_reaches_own_authentication_without_login_redirect(self, read):
        from ColorAdminApp.middleware import SupabaseAuthMiddleware
        req = self.request('/integracoes/agenda-regional/api/buscar/', method='post');req.session={}
        response = SupabaseAuthMiddleware(lambda request: HttpResponse('endpoint'))(req)
        self.assertEqual(response.content, b'endpoint')
        read.assert_not_called()

    @patch.object(agenda.requests, 'post')
    def test_sql_conflict_is_reported_as_conflict(self, post):
        post.return_value = Mock(ok=False)
        post.return_value.json.return_value = {'code':'23P01','message':'Horário ocupado'}
        with self.assertRaises(agenda.AgendaError) as raised:
            agenda.rpc('agenda_operar', {})
        self.assertEqual(raised.exception.status, 409)

    @patch.object(agenda, 'read', side_effect=requests.Timeout())
    def test_database_outage_does_not_return_empty_calendar(self, _read):
        self.assertEqual(agenda.events_api(self.request()).status_code, 503)

    @patch.object(agenda.requests, 'post')
    def test_missing_migration_has_actionable_error(self, post):
        post.return_value = Mock(ok=False)
        post.return_value.json.return_value = {'code':'PGRST202'}
        with self.assertRaises(agenda.AgendaError) as raised:
            agenda.rpc('agenda_operar', {})
        self.assertEqual(raised.exception.status, 503)
        self.assertIn('064', str(raised.exception))

    @patch.object(agenda, 'rpc')
    def test_old_four_calendar_worker_cannot_claim_municipal_work(self, rpc):
        response=agenda.integration_api(self.request(method='post',token='Bearer worker-secret'),'buscar')
        self.assertEqual(response.status_code,409);rpc.assert_not_called()

    @patch.object(agenda, 'operate',return_value={'ok':True})
    def test_calendar_configuration_targets_municipality_not_administration(self, operate):
        response=agenda.configuration_api(self.request(method='post',payload={
            'tipo':'agenda','agenda_id':'caucaia','calendar_id':'caucaia@group.calendar.google.com'}))
        self.assertEqual(response.status_code,200)
        self.assertEqual(operate.call_args.args[1]['agenda_id'],'caucaia')

    @patch.object(agenda, 'operate')
    def test_shared_configuration_payload_without_municipality_is_rejected(self, operate):
        response=agenda.configuration_api(self.request(method='post',payload={
            'tipo':'agenda','administracao_id':'cotia','calendar_id':'shared@group.calendar.google.com'}))
        self.assertEqual(response.status_code,400);operate.assert_not_called()

    @patch.object(agenda,'roles',return_value=[])
    @patch.object(agenda,'read')
    def test_existing_google_event_is_merged_into_calendar_without_local_reservation(self,read,_roles):
        from ColorAdminApp.modules.regional_agenda_google import presentation
        row={'id':self.event_id,'agenda_id':'itapevi','administracao_id':'itapevi','municipio':'Itapevi',
             'titulo':'Evento já existente','local':'Central','inicio':'2026-11-23T19:00:00-03:00',
             'fim':'2026-11-23T21:00:00-03:00','disponivel':False}
        agenda.google_window.return_value=([presentation(row)],{'instalada':True,'pending':0,'leituras':[]})
        read.side_effect=[[{'id':'itapevi','nome':'Itapevi','municipios':['Itapevi'],'prazo_horas':48}],
                          [{**c,'calendar_id':'cal-'+c['id']} for c in agenda.CALENDAR_BY_ID.values()],[]]
        response=agenda.events_api(self.request());data=json.loads(response.content)
        self.assertEqual(data['events'][0]['titulo'],'Evento já existente')
        self.assertTrue(data['events'][0]['somente_leitura'])
        self.assertEqual(data['events'][0]['status'],'GOOGLE')

    @patch.object(agenda,'rpc',return_value={'ok':True})
    @patch.object(agenda,'read',return_value=[{'calendar_id':'calendar-test'}])
    def test_incomplete_google_payload_records_failure_instead_of_erasing_snapshot(self,_read,rpc):
        req=self.request(method='post',token='Bearer worker-secret',payload={'id':self.event_id,
            'lease_token':str(uuid4()),'resultado':'ok','eventos':[{'id':'g1','start':{},'end':{}}]})
        response=agenda.integration_api(req,'resultado_leitura')
        self.assertEqual(response.status_code,200)
        payload=rpc.call_args.args[1]['p_dados']
        self.assertEqual(payload['resultado'],'erro');self.assertNotIn('eventos',payload)
