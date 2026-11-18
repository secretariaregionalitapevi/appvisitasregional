from unittest.mock import Mock,patch
from uuid import uuid4
from django.test import SimpleTestCase,override_settings
from django.core.cache.backends.locmem import LocMemCache
from ColorAdminApp.modules import regional_route_roads as roads
from ColorAdminApp.modules.regional_routes import finalize_plan
from .tests_regional_routes import members,teams,DAY,COMMONS


@override_settings(GOOGLE_MAPS_API_KEY='offline-key')
class RegionalRoadOrderTests(SimpleTestCase):
    def setUp(self):
        patcher=patch.object(roads,'cache',LocMemCache(str(uuid4()),{}))
        patcher.start();self.addCleanup(patcher.stop)

    @patch.object(roads.requests,'get')
    def test_matrix_is_cached_and_uses_road_distances(self,get):
        get.return_value=Mock(json=lambda:{'status':'OK','rows':[
            {'elements':[{'status':'OK','distance':{'value':v}} for v in row]} for row in [[0,100],[150,0]]]})
        points=[[-23.54,-46.98],[-23.54,-46.97]]
        first=roads.road_matrix(points)
        self.assertEqual(first,roads.road_matrix(list(reversed(points))))
        self.assertEqual(sorted(first.values()),[0,0,100,150])
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs['params']['mode'],'driving')

    @patch.object(roads.requests,'get')
    def test_denied_matrix_does_not_create_fake_road_distances(self,get):
        get.return_value=Mock(json=lambda:{'status':'REQUEST_DENIED'})
        self.assertEqual(roads.road_matrix([[-23.54,-46.98],[-23.54,-46.97]]),{})

    def test_jurema_road_sequence_visits_passed_houses_before_returning(self):
        points=[[-23.5475132,-46.9948955],[-23.548204988962,-46.994187974834],
                [-23.547384987374,-46.993693023451],[-23.54708499906,-46.993360010438]]
        matrix=[[0,532,413,367],[532,0,119,165],[413,119,0,47],[367,165,47,0]]
        people=members(4)
        houses=[]
        for index,person in enumerate(people):
            person['preferencia_periodo_visita']='Manhã'
            houses.append({'key':str(index),'group_id':'0','number':index+1,'members':[person],
                           'coords':points[index],'address':person['endereco'],'bairro':''})
        distances={roads.road_key(a,b):matrix[i][j] for i,a in enumerate(points) for j,b in enumerate(points)}
        plan={'houses':houses,'groups':teams(1),'commons':COMMONS,'date':DAY,'road_distances':distances}
        finalize_plan(plan)
        self.assertEqual([h['key'] for h in plan['houses']],['0','3','2','1'])
        self.assertEqual([h['start'][11:16] for h in plan['houses']],['09:00','09:15','09:30','09:45'])
        self.assertEqual([h['number'] for h in plan['houses']],[1,2,3,4])
        self.assertEqual(sum(distances[roads.road_key(a['coords'],b['coords'])] for a,b in zip(plan['houses'],plan['houses'][1:])),533)

    @patch.object(roads.requests,'get')
    def test_large_matrices_are_split_into_at_most_one_hundred_elements(self,get):
        def response(*args,**kwargs):
            params=kwargs['params'];a=len(params['origins'].split('|'));b=len(params['destinations'].split('|'))
            self.assertLessEqual(a*b,100)
            return Mock(json=lambda:{'status':'OK','rows':[{'elements':[{'status':'OK','distance':{'value':1}}]*b} for _ in range(a)]})
        get.side_effect=response
        result=roads.road_matrix([[-23.54,-46.98+i*.001] for i in range(12)])
        self.assertEqual(len(result),144)
        self.assertEqual(get.call_count,2)

    def test_road_shortcut_cannot_move_afternoon_houses_into_morning(self):
        points=[[-23.54,-46.98+i*.001] for i in range(4)]
        matrix=[[0,500,10,20],[500,0,490,480],[10,490,0,10],[20,480,10,0]]
        houses=[{'key':str(i),'number':i+1,'group_id':'0','coords':point,'address':str(i),'bairro':'',
                 'members':[{'comum':COMMONS[0],'preferencia_periodo_visita':'Manhã' if i<2 else 'Tarde'}]}
                for i,point in enumerate(points)]
        plan={'houses':houses,'groups':teams(1),'commons':COMMONS,'date':DAY,
              'road_distances':{roads.road_key(a,b):matrix[i][j] for i,a in enumerate(points) for j,b in enumerate(points)}}
        finalize_plan(plan)
        self.assertEqual([h['key'] for h in plan['houses'][:2]],['0','1'])
        self.assertTrue(all(h['start'][11:16]>='14:00' for h in plan['houses'][2:]))
