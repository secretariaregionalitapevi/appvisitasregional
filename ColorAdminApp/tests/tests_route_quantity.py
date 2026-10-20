from unittest.mock import Mock,patch
from django.test import SimpleTestCase,RequestFactory
from ColorAdminApp.utils.routing import auto_dispatch_visits,route_household_target
from ColorAdminApp.views import visitasRoteiro

class RouteQuantityTests(SimpleTestCase):
    @patch('ColorAdminApp.views.user_scope')
    def test_invalid_quantity_is_rejected_before_any_query(self,scope):
        for quantity in ['0','11','6.5','abc','-1','']:
            result=visitasRoteiro(RequestFactory().get('/visitas/roteiro/',{'casas':quantity}))
            self.assertEqual(result.status_code,400)
        scope.assert_not_called()

    def dispatch(self,target,existing=None):
        members=[{'id':str(i),'nome':'Casa '+str(i),'comum':'COMUM','setor':'Centro','status':'Ativo','endereco':'[-23.54, -46.98] Rua Teste, '+str(i)} for i in range(1,15)]
        def created(*args,**kwargs):return Mock(status_code=201,json=lambda:kwargs['json'])
        with patch('ColorAdminApp.utils.routing.get_common_coordinates',return_value=(-23.54,-46.98)),patch('ColorAdminApp.utils.routing.requests.get',side_effect=[Mock(status_code=200,json=lambda:members),Mock(status_code=200,json=lambda:[])]) as get,patch('ColorAdminApp.utils.routing.requests.post',side_effect=created) as post:
            rows=auto_dispatch_visits('Grupo A','2026-10-24',existing_visits=existing,comum='COMUM',target_houses=target)
            return rows,post,get

    def test_six_houses_are_three_in_each_shift(self):
        rows,post,_=self.dispatch(6)
        self.assertEqual(len(rows),6)
        self.assertEqual(sum('T09:' in row['data_inicio'] for row in rows),3)
        self.assertEqual(sum('T14:' in row['data_inicio'] for row in rows),3)

    def test_seven_houses_are_four_morning_and_three_afternoon(self):
        rows,_,_=self.dispatch(7)
        self.assertEqual(len(rows),7)
        self.assertEqual(sum('T09:' in row['data_inicio'] for row in rows),4)

    def test_existing_residents_at_same_address_count_as_one_house(self):
        existing=[{'endereco_visitado':'[-23.54, -46.98] Rua Teste, 1','data_inicio':'2026-10-24T09:00:00-03:00'},{'endereco_visitado':'[-23.54, -46.98] Rua Teste, 1','data_inicio':'2026-10-24T09:00:00-03:00'}]
        rows,_,_=self.dispatch(6,existing)
        self.assertEqual(len(rows),5)
        self.assertTrue(all('09:00:00' not in r['data_inicio'] for r in rows))

    def test_raising_six_to_seven_fills_free_slot_without_colliding_with_utc_times(self):
        existing=[{'endereco_visitado':'[-23.54, -46.98] Rua Teste, '+str(i+1),'data_inicio':f'2026-10-24T{hour}:{minute}:00+00:00'} for i,(hour,minute) in enumerate([('12','00'),('12','15'),('12','30'),('17','00'),('17','15'),('17','30')])]
        rows,_,_=self.dispatch(7,existing)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['data_inicio'],'2026-10-24T09:45:00-03:00')

    def test_lower_target_preserves_existing_visits_without_writing(self):
        existing=[{'endereco_visitado':'[-23.54, -46.98] Rua Teste, '+str(i)} for i in range(1,8)]
        rows,post,get=self.dispatch(6,existing)
        self.assertEqual(rows,[]);post.assert_not_called();get.assert_not_called()
        self.assertEqual(len(existing),7)

    def test_default_target_remains_ten(self):
        self.assertEqual(route_household_target(),10)
        rows,_,_=self.dispatch(10)
        self.assertEqual(len(rows),10)

    @patch('ColorAdminApp.views.render',side_effect=lambda req, template, context:context)
    @patch('ColorAdminApp.views.user_scope',return_value={'level':'global'})
    @patch('ColorAdminApp.views.visible_commons',return_value=[{'comum':'COMUM','cidade':'ITAPEVI'}])
    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.utils.routing.auto_dispatch_visits',return_value=[])
    @patch('ColorAdminApp.utils.routing.get_common_coordinates',return_value=(-23.54,-46.98))
    def test_form_quantity_reaches_dispatch_and_print_context(self,origin,dispatch,get,commons,scope,render):
        get.side_effect=[Mock(status_code=200,json=lambda:[]),Mock(status_code=200,json=lambda:[{'id':'a','tipo':'REGIONAL','ativo':True}])]
        req=RequestFactory().get('/visitas/roteiro/',{'comum':'COMUM','equipe':'Grupo A','data':'2026-10-24','casas':'7'})
        context=visitasRoteiro(req)
        self.assertEqual(dispatch.call_args.kwargs['target_houses'],7)
        self.assertEqual((context['meta_casas'],context['meta_manha'],context['meta_tarde']),(7,4,3))

    @patch('ColorAdminApp.views.render',side_effect=lambda req, template, context:context)
    @patch('ColorAdminApp.views.user_scope',return_value={'level':'global'})
    @patch('ColorAdminApp.views.visible_commons',return_value=[{'comum':'COMUM','cidade':'ITAPEVI'}])
    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.utils.routing.auto_dispatch_visits')
    @patch('ColorAdminApp.utils.routing.get_common_coordinates',return_value=(-23.54,-46.98))
    def test_changing_neighborhood_does_not_allow_exceeding_group_target(self,origin,dispatch,get,commons,scope,render):
        visits=[{'id':'v'+str(i),'irmandade_id':str(i),'titulo':'Casa','equipe_responsavel':'Grupo A','status':'Marcada','setor':'Bairro A' if i<2 else 'Bairro B','endereco_visitado':'[-23.54, -46.98] Rua Teste, '+str(i),'data_inicio':'2026-10-24T12:00:00+00:00'} for i in range(6)]
        members=[{'id':str(i),'comum':'COMUM'} for i in range(6)]
        get.side_effect=[Mock(status_code=200,json=lambda:visits),Mock(status_code=200,json=lambda:members),Mock(status_code=200,json=lambda:members),Mock(status_code=200,json=lambda:[])]
        req=RequestFactory().get('/visitas/roteiro/',{'comum':'COMUM','equipe':'Grupo A','data':'2026-10-24','casas':'6','bairro':'Bairro A'})
        context=visitasRoteiro(req)
        self.assertEqual(len(context['roteiro']),2)
        dispatch.assert_not_called()
