import json
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, RequestFactory, override_settings
from ColorAdminApp.views import apiVisitasAgenda, visitasRoteiro
from ColorAdminApp.utils import routing

COMMON = 'BR-22-2054 - CH\u00c1CARA REGINA'
LEGACY = 'BR-22-2054 - Ch\u00e1cara Regina'
CATALOG = [{'comum': COMMON, 'cidade': 'ITAPEVI'}]
ORIGIN = (-23.5407, -46.9864)

def response(rows, status=200):
    return Mock(status_code=status, json=lambda: rows)

class RouteIntegrityTests(SimpleTestCase):
    def tearDown(self):
        routing.geocode_address_fallback.cache_clear()

    @patch('ColorAdminApp.views.log_audit')
    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.views.visible_commons', return_value=CATALOG)
    @patch('ColorAdminApp.views.user_scope', return_value={'level': 'global'})
    def test_calendar_finds_saved_visits_when_common_case_differs(self, scope, commons, get, audit):
        get.side_effect = [response([{'id': 'v1', 'irmandade_id': 'm1', 'data_inicio': '2026-10-17T12:00:00+00:00', 'titulo': 'Casa', 'observacoes': ''}]), response([{'id': 'm1', 'comum': LEGACY}])]
        req=RequestFactory().get('/visitas/api/agenda/', {'comum': COMMON, 'start_date': '2026-10-17T00:00:00-03:00', 'end_date': '2026-10-18T00:00:00-03:00'})
        result=apiVisitasAgenda(req)
        self.assertEqual(result.status_code,200)
        self.assertEqual([r['id'] for r in json.loads(result.content)], ['v1'])
        self.assertEqual(json.loads(result.content)[0]['comum'],COMMON)
        audit.assert_not_called()

    @patch('ColorAdminApp.utils.routing.get_common_coordinates', return_value=ORIGIN)
    @patch('ColorAdminApp.utils.routing.auto_dispatch_visits')
    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.views.visible_commons', return_value=CATALOG)
    @patch('ColorAdminApp.views.user_scope', return_value={'level': 'global'})
    @patch('ColorAdminApp.views.render', side_effect=lambda req, template, context: context)
    def test_regenerating_saved_route_does_not_duplicate_or_mix_commons(self, render, scope, commons, get, dispatch, common_coords):
        visits=[{'id': 'v'+str(i), 'irmandade_id': 'm'+str(i), 'titulo': 'Casa '+str(i), 'endereco_visitado':'Rua Nimbus, '+str(i), 'equipe_responsavel':'Grupo A','data_inicio':'2026-10-17T12:00:00+00:00','status':'Marcada'} for i in range(10)]
        members=[{'id':'m'+str(i), 'comum':LEGACY,'endereco':'[-23.5407, -46.9864] Rua Nimbus, '+str(i)} for i in range(10)]
        visits.append({'id':'foreign','irmandade_id':'other','equipe_responsavel':'Grupo A'})
        members.append({'id':'other','comum':'OUTRA COMUM','endereco':'Rua Outra, 1'})
        get.side_effect=[response(visits),response(members),response([{'id':'m'+str(i),'equipe_id':None,'equipe_visita':None} for i in range(10)]),response([])]
        req=RequestFactory().get('/visitas/roteiro/',{'comum':COMMON,'equipe':'Grupo A','data':'2026-10-17'})
        context=visitasRoteiro(req)
        self.assertEqual(len(context['roteiro']),10)
        self.assertNotIn('foreign',[v['id'] for v in context['roteiro']])
        dispatch.assert_not_called()
        self.assertTrue(all(abs(v['lat']-ORIGIN[0])<0.001 for v in context['roteiro']))
        self.assertIn(('data_inicio','gte.2026-10-17T00:00:00-03:00'),get.call_args_list[0].kwargs['params'])

    @patch('ColorAdminApp.utils.routing.geocode_address_fallback', return_value=(-23.5406,-46.9864))
    def test_legacy_nimbus_coordinate_in_other_city_is_replaced(self, geocode):
        coords=routing.resolve_visit_coordinates('[-21.2922457, -50.3428431] Rua Nimbus, 190','ITAPEVI','Parque Miraflores',ORIGIN)
        self.assertLess(routing.haversine_distance(coords,ORIGIN),30)
        geocode.assert_called_once_with('Rua Nimbus, 190',city='ITAPEVI',neighborhood='Parque Miraflores')

    @patch('ColorAdminApp.utils.routing.geocode_address_fallback', return_value=None)
    def test_unresolved_outlier_never_becomes_map_coordinate_or_distance(self, geocode):
        visit={'endereco_visitado':'[-21.2922457, -50.3428431] Rua Nimbus, 190','municipio':'ITAPEVI','setor':'Parque Miraflores','_route_origin':ORIGIN,'lat':-21.29,'lng':-50.34}
        result=routing.order_route_chronologically([visit],ORIGIN)[0]
        for field in ['lat','lng','distance_meters']:
            self.assertNotIn(field,result)

    @override_settings(GOOGLE_MAPS_API_KEY='test')
    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_geocoder_rejects_other_city_even_with_high_score(self,get):
        google={'status':'OK','results':[{'geometry':{'location':{'lat':-21.29,'lng':-50.34}},'address_components':[{'long_name':'Outra cidade','types':['administrative_area_level_2']},{'short_name':'SP','types':['administrative_area_level_1']}]}]}
        arcgis={'candidates':[{'score':100,'location':{'y':-21.29,'x':-50.34},'attributes':{'City':'Outra cidade','RegionAbbr':'SP','Addr_type':'PointAddress'}}]}
        get.side_effect=[response(google),response(arcgis)]
        self.assertIsNone(routing.geocode_address_fallback('Rua Nimbus, 190',city='ITAPEVI'))
        self.assertIn('ITAPEVI',get.call_args_list[0].kwargs['params']['address'])

    @patch('ColorAdminApp.utils.routing.get_common_coordinates',return_value=ORIGIN)
    @patch('ColorAdminApp.utils.routing.requests.post',return_value=response({'error':'failure'},500))
    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_failed_insert_is_reported_and_never_returns_a_fake_route(self,get,post,origin):
        member={'id':'m','nome':'Casa','comum':COMMON,'endereco':'[-23.5407, -46.9864] Rua Nimbus, 190','status':'Ativo'}
        get.side_effect=[response([member]),response([])]
        with self.assertRaisesRegex(RuntimeError,'Falha ao gravar'):
            routing.auto_dispatch_visits('Grupo A','2026-10-17',comum=COMMON,cidade='ITAPEVI',equipe_id='team-a',equipe_tipo='REGIONAL')
        self.assertEqual(post.call_args.kwargs['json'][0]['equipe_id'],'team-a')

    @override_settings(GOOGLE_MAPS_API_KEY='test')
    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_geocoder_accepts_confirmed_itapevi_street_address(self, get):
        result={'status':'OK','results':[{'types':['street_address'], 'geometry':{'location':{'lat':-23.5402959,'lng':-46.9864783}},'address_components':[{'long_name':'Itapevi','types':['administrative_area_level_2']},{'short_name':'SP','types':['administrative_area_level_1']}]}]}
        get.return_value=response(result)
        self.assertEqual(routing.geocode_address_fallback('Rua Nimbus, 190',city='ITAPEVI'),(-23.5402959,-46.9864783))

    @override_settings(GOOGLE_MAPS_API_KEY='test')
    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_city_center_is_not_accepted_as_a_house(self,get):
        google={'status':'OK','results':[{'types':['locality'], 'geometry':{'location':{'lat':-23.54,'lng':-46.98}},'address_components':[{'long_name':'Itapevi','types':['administrative_area_level_2']},{'short_name':'SP','types':['administrative_area_level_1']}]}]}
        get.side_effect=[response(google),response({'candidates':[]})]
        self.assertIsNone(routing.geocode_address_fallback('Rua Nimbus, 190',city='ITAPEVI'))
