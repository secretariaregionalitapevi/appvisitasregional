import itertools
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase,RequestFactory
from ColorAdminApp.utils.routing import optimize_linear_route,plan_linear_schedule,haversine_distance
from ColorAdminApp.utils.route_schedule import persist_suggested_schedule
from ColorAdminApp.views import visitasRoteiro

ORIGIN=(-23.54,-46.986)
def visit(i,x,start='2026-10-24T09:00:00-03:00',end='2026-10-24T09:15:00-03:00'):
    return {'id':str(i),'titulo':str(i),'status':'Marcada','endereco_visitado':f'[-23.54, {x}] Rua {i}, 10','data_inicio':start,'data_fim':end}
def length(route):
    coords=[ORIGIN]+[(v['lat'],v['lng']) for v in route]
    return sum(haversine_distance(a,b) for a,b in zip(coords,coords[1:]))

class LinearRouteTests(SimpleTestCase):
    def test_closer_stop_is_not_postponed_until_after_eastern_extreme(self):
        visits=[visit(1,-46.987),visit(2,-47.01),visit(3,-47.02),visit(4,-46.92),visit(5,-46.98)]
        route=optimize_linear_route(visits,ORIGIN)
        ids=[v['id'] for v in route]
        self.assertLess(ids.index('5'),ids.index('4'))
        self.assertEqual(ids,['1','2','3','5','4'])

    def test_open_path_is_optimal_over_all_permutations(self):
        visits=[visit(i,x) for i,x in enumerate([-46.98,-47.01,-46.985,-46.93])]
        route=optimize_linear_route(visits,ORIGIN)
        minimum=min(length(optimize_coordinates_only(p)) for p in itertools.permutations(visits))
        self.assertAlmostEqual(length(route),minimum,places=5)

    def test_equal_coordinates_keep_stable_order(self):
        visits=[visit(i,ORIGIN[1]) for i in range(7)]
        self.assertEqual([v['id'] for v in optimize_linear_route(visits,ORIGIN)],[str(i) for i in range(7)])

    def test_schedule_follows_whole_route_across_morning_afternoon_boundary(self):
        visits=[visit(1,-46.987),visit(4,-46.92,'2026-10-24T09:15:00-03:00','2026-10-24T09:30:00-03:00'),visit(5,-46.98,'2026-10-24T14:00:00-03:00','2026-10-24T14:15:00-03:00')]
        route=plan_linear_schedule(visits,ORIGIN)
        self.assertEqual([v['id'] for v in route],['1','5','4'])
        self.assertEqual([v['data_inicio'] for v in route],sorted(v['data_inicio'] for v in visits))
        self.assertEqual(visits[1]['data_inicio'],'2026-10-24T09:15:00-03:00')

    def test_replanning_is_idempotent(self):
        route=plan_linear_schedule([visit(4,-46.92),visit(5,-46.98)],ORIGIN)
        again=plan_linear_schedule(route,ORIGIN)
        self.assertEqual([(v['id'],v['data_inicio']) for v in route],[(v['id'],v['data_inicio']) for v in again])

    @patch('ColorAdminApp.views.render',side_effect=lambda req,template,context:context)
    @patch('ColorAdminApp.views.user_scope',return_value={'level':'global'})
    @patch('ColorAdminApp.views.visible_commons',return_value=[{'comum':'COMUM','cidade':'ITAPEVI'}])
    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.utils.routing.get_common_coordinates',return_value=ORIGIN)
    @patch('ColorAdminApp.utils.route_schedule.persist_suggested_schedule')
    def test_view_keeps_same_order_in_route_map_and_saved_schedule(self,persist,origin,get,commons,scope,render):
        visits=[visit(1,-46.987),visit(4,-46.92,'2026-10-24T09:15:00-03:00','2026-10-24T09:30:00-03:00'),visit(5,-46.98,'2026-10-24T14:00:00-03:00','2026-10-24T14:15:00-03:00')]
        for v in visits:v.update({'irmandade_id':v['id'],'equipe_responsavel':'Grupo A'})
        members=[{'id':v['id'],'comum':'COMUM'} for v in visits]
        get.side_effect=[Mock(status_code=200,json=lambda:visits),Mock(status_code=200,json=lambda:members),Mock(status_code=200,json=lambda:members),Mock(status_code=200,json=lambda:[])]
        context=visitasRoteiro(RequestFactory().get('/visitas/roteiro/',{'comum':'COMUM','equipe':'Grupo A','data':'2026-10-24','casas':'3','mapa':'demo'}))
        self.assertEqual([v['id'] for v in context['roteiro']],['1','5','4'])
        self.assertEqual([v['title'] for v in context['route_map_points']],['1','5','4'])
        self.assertEqual([v['id'] for v in persist.call_args.args[0]],['1','5','4'])
        self.assertEqual([v['route_period'] for v in context['roteiro']],['manha','manha','tarde'])


def optimize_coordinates_only(visits):
    return [{**v,'lat':-23.54,'lng':float(v['endereco_visitado'].split(', ')[1].split(']')[0])} for v in visits]

class SuggestedSchedulePersistenceTests(SimpleTestCase):
    @patch('ColorAdminApp.utils.route_schedule.requests.patch')
    def test_changed_slot_is_saved_once_with_concurrency_guard(self,patch_request):
        original=visit(1,-46.98)
        planned={**original,'data_inicio':'2026-10-24T14:00:00-03:00','data_fim':'2026-10-24T14:15:00-03:00'}
        patch_request.return_value=Mock(json=lambda:[planned]);changes=[]
        persist_suggested_schedule([planned],[original],changes)
        patch_request.assert_called_once()
        self.assertEqual(patch_request.call_args.kwargs['params']['data_inicio'],'eq.'+original['data_inicio'])
        self.assertEqual(len(changes),1)

    @patch('ColorAdminApp.utils.route_schedule.requests.patch')
    def test_unchanged_slot_is_not_written(self,patch_request):
        original=visit(1,-46.98);changes=[]
        persist_suggested_schedule([original],[original],changes)
        patch_request.assert_not_called();self.assertEqual(changes,[])

    @patch('ColorAdminApp.utils.route_schedule.supabase_get')
    @patch('ColorAdminApp.utils.route_schedule.requests.patch',side_effect=requests.Timeout())
    def test_uncertain_write_is_verified_without_resending(self,patch_request,get):
        original=visit(1,-46.98);planned={**original,'data_inicio':'2026-10-24T14:00:00-03:00','data_fim':'2026-10-24T14:15:00-03:00'}
        get.return_value=Mock(json=lambda:[planned]);changes=[]
        persist_suggested_schedule([planned],[original],changes)
        patch_request.assert_called_once();get.assert_called_once();self.assertEqual(len(changes),1)

    @patch('ColorAdminApp.utils.route_schedule.requests.patch')
    def test_concurrent_change_is_not_overwritten(self,patch_request):
        original=visit(1,-46.98);planned={**original,'data_inicio':'2026-10-24T14:00:00-03:00'}
        patch_request.return_value=Mock(json=lambda:[])
        with self.assertRaisesRegex(ValueError,'alterada durante'):
            persist_suggested_schedule([planned],[original],[])
        patch_request.assert_called_once()

    @patch('ColorAdminApp.utils.route_schedule.requests.patch')
    def test_completed_visit_cannot_be_rescheduled(self,patch_request):
        original={**visit(1,-46.98),'status':'Realizada'}
        with self.assertRaises(ValueError):persist_suggested_schedule([original],[original],[])
        patch_request.assert_not_called()
