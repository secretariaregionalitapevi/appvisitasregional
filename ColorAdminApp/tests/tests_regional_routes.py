import json
import requests
import io
import zipfile
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core import signing
from django.test import RequestFactory, SimpleTestCase

from ColorAdminApp.modules.regional_routes import build_plan, finalize_plan
from ColorAdminApp.modules import regional_route_views as views


DAY = '2099-10-17'
COMMONS = ['JARDIM RUTH', 'VILA DAS CHACARAS']


def teams(count=7):
    return [{'id':str(i),'nome':'Grupo '+chr(65+i),'ativo':True,'confirmado':True,
             'coordenador_nome':'Coordenador '+str(i)} for i in range(count)]


def members(count=7):
    return [{'id':str(i),'nome':'Familia '+str(i),'comum':COMMONS[i%2],
             'endereco':f'[-23.54, {-46.98+i/10000}] Rua das Familias, {i+1}',
             'setor':'Vila das Chacaras','status':'Ativo'} for i in range(count)]


class RegionalDistributionTests(SimpleTestCase):
    def plan(self, count=7, group_count=7, agenda=None, people=None, **kwargs):
        return build_plan(people or members(count), agenda or [], teams(group_count), DAY,
                          'ITAPEVI', COMMONS, **kwargs)

    def test_seven_houses_receive_seven_distinct_groups(self):
        plan = self.plan()
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[1]*7)

    def test_selected_common_without_eligible_people_remains_visible_in_coverage(self):
        people=members(3)
        for person in people:person['comum']='VILA BELMIRA'
        plan=build_plan(people,[],teams(2),DAY,'ITAPEVI',['VILA BELMIRA','CHACARA REGINA'])
        self.assertEqual([(c['common'],c['families']) for c in plan['coverage']],[('VILA BELMIRA',3),('CHACARA REGINA',0)])

    def test_regina_and_belmira_all_eligible_families_are_included(self):
        people=members(59)
        for i,person in enumerate(people):person['comum']='CHACARA REGINA' if i<39 else 'VILA BELMIRA'
        plan=build_plan(people,[],teams(5),DAY,'ITAPEVI',['VILA BELMIRA','CHACARA REGINA'])
        self.assertEqual(len(plan['houses']),59)
        self.assertEqual(sorted(c['included_records'] for c in plan['coverage']),[20,39])

    def test_uneven_households_are_balanced_with_at_most_one_difference(self):
        plan = self.plan(count=49)
        self.assertEqual(set(Counter(h['group_id'] for h in plan['houses']).values()),{7})
        plan = self.plan(count=50)
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[7]*6+[8])

    def test_all_sixty_houses_are_distributed_without_a_per_group_limit(self):
        plan = self.plan(count=60)
        self.assertEqual(len(plan['houses']),60)
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[8,8,8,9,9,9,9])

    def test_one_hundred_families_from_three_commons_receive_four_equal_groups(self):
        people=members(100)
        commons=['COMUM A','COMUM B','COMUM C']
        for index,person in enumerate(people):person['comum']=commons[index%3]
        plan=finalize_plan(build_plan(people,[],teams(4),DAY,'ITAPEVI',commons))
        self.assertEqual(len(plan['houses']),100)
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[25]*4)
        self.assertEqual(len({m['id'] for h in plan['houses'] for m in h['members']}),100)

    def test_fifty_six_families_and_three_groups_include_old_and_remaining_visits(self):
        people=members(56)
        agenda=[{'id':'visit-'+m['id'],'irmandade_id':m['id'],'status':'Marcada',
                 'data_inicio':DAY+'T09:00:00-03:00','equipe_id':str(i%3)} for i,m in enumerate(people[:24])]
        plan=self.plan(group_count=3,people=people,agenda=agenda)
        self.assertEqual(len(plan['houses']),56)
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[18,19,19])
        self.assertEqual(sum(len(h['visit_ids']) for h in plan['houses']),24)

    def test_remainder_is_distributed_without_omitting_any_family(self):
        plan=self.plan(count=101,group_count=4)
        self.assertEqual(len(plan['houses']),101)
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[25,25,25,26])

    def test_same_address_across_commons_is_one_house_with_both_origins(self):
        people = members(2)
        people[1]['endereco']=people[0]['endereco']
        plan = self.plan(people=people)
        self.assertEqual(len(plan['houses']),1)
        self.assertEqual({m['comum'] for m in plan['houses'][0]['members']},set(COMMONS))

    def test_seven_visits_previously_on_a_are_rebalanced_and_not_recreated(self):
        people=members()
        agenda=[{'id':'visit-'+m['id'],'irmandade_id':m['id'],'status':'Marcada',
                 'data_inicio':DAY+'T09:00:00-03:00','equipe_id':'0','equipe_responsavel':'Grupo A'} for m in people]
        plan=self.plan(agenda=agenda,people=people)
        self.assertEqual(len({h['group_id'] for h in plan['houses']}),7)
        self.assertTrue(all(len(h['visit_ids'])==1 for h in plan['houses']))

    def test_completed_and_local_team_visits_do_not_move(self):
        agenda=[{'id':'v0','irmandade_id':'0','status':'Realizada','data_inicio':DAY+'T09:00:00-03:00','equipe_id':'0'},
                {'id':'v1','irmandade_id':'1','status':'Marcada','data_inicio':DAY+'T09:00:00-03:00','equipe_id':'local','equipe_responsavel':'Equipe 1'}]
        plan=self.plan(agenda=agenda)
        self.assertEqual(len(plan['houses']),5)
        self.assertFalse(any(h['visit_ids'] for h in plan['houses']))

    def test_visitors_and_inactive_members_are_not_visit_destinations(self):
        people=members(3);people[0]['grupo_regional_id']='0';people[1]['status']='Inativo'
        self.assertEqual(len(self.plan(people=people)['houses']),1)

    def test_only_confirmed_groups_and_the_daily_coordinator_are_used(self):
        group_list=teams();group_list[0]['confirmado']=False;group_list[1]['coordenador_nome']='Manoel'
        plan=build_plan(members(),[],group_list,DAY,'ITAPEVI',COMMONS)
        self.assertNotIn('0',{h['group_id'] for h in plan['houses']})
        self.assertEqual(plan['groups'][0]['coordenador_nome'],'Manoel')
        self.assertEqual(teams()[1]['coordenador_nome'],'Coordenador 1')

    def test_manual_assignments_have_no_per_group_ceiling_but_require_confirmed_groups(self):
        plan=self.plan(count=30,group_count=2)
        assignments={h['key']:'0' for h in plan['houses']}
        changed=finalize_plan(deepcopy(plan),assignments)
        self.assertEqual(Counter(h['group_id'] for h in changed['houses']),{'0':30})
        assignments[plan['houses'][0]['key']]='not-confirmed'
        with self.assertRaisesRegex(ValueError,'confirmados'):finalize_plan(plan,assignments)

    def test_default_and_afternoon_preferences_never_share_a_time(self):
        people=members(8);people[0]['preferencia_periodo_visita']='Tarde'
        plan=finalize_plan(self.plan(group_count=1,people=people))
        self.assertEqual(len({h['start'] for h in plan['houses']}),8)
        first=next(h for h in plan['houses'] if h['members'][0]['id']=='0')
        self.assertGreaterEqual(first['start'][11:16],'14:00')

    def test_morning_precedes_afternoon_in_numbering_and_saved_export(self):
        from ColorAdminApp.modules.regional_route_reports import decorate_groups
        people = members(7)
        for index, person in enumerate(people):
            person['preferencia_periodo_visita'] = 'Tarde' if index < 3 else 'Manhã'
        plan = finalize_plan(self.plan(group_count=1, people=people))
        houses = sorted(plan['houses'], key=lambda h: h['number'])
        self.assertEqual([h['start'][11:16] for h in houses],
                         ['09:00','09:15','09:30','09:45','14:00','14:15','14:30'])
        group = {**plan['groups'][0], 'houses': list(reversed(houses))}
        starts = {h['key']: h['start'] for h in group['houses']}
        decorate_groups([group])
        self.assertEqual([h['number'] for h in group['houses']], list(range(1,8)))
        self.assertEqual([h['period'] for h in group['houses']], ['Manhã']*4+['Tarde']*3)
        self.assertEqual({h['key']:h['start'] for h in group['houses']},starts)

    def test_nearby_houses_stay_together_inside_each_period(self):
        from ColorAdminApp.modules.regional_routes import period_route_order
        origin = (-23.54, -46.98)
        # Entrada intercalada e fora de ordem: perto/longe/perto em cada periodo.
        specs = [('m1',.0001,'Manhã'),('a3',.0200,'Tarde'),
                 ('m3',.0100,'Manhã'),('a1',.0101,'Tarde'),
                 ('m2',.0002,'Manhã'),('a2',.0102,'Tarde')]
        houses = [{'key':key,'coords':(origin[0],origin[1]+delta),
                   'bairro':'','address':'Rua '+key,'members':[{'preferencia_periodo_visita':period}]}
                  for key,delta,period in specs]
        result = period_route_order(houses,origin,3)
        self.assertEqual([(hour,h['key']) for hour,h in result],
                         [(9,'m1'),(9,'m2'),(9,'m3'),(14,'a1'),(14,'a2'),(14,'a3')])

    def test_route_optimizer_receives_each_period_separately(self):
        from ColorAdminApp.modules.regional_routes import period_route_order
        people = members(6)
        for index,person in enumerate(people):
            person['preferencia_periodo_visita'] = 'Manhã' if index%2 else 'Tarde'
        houses = self.plan(group_count=1,people=people)['houses']
        origin = (-23.54,-46.98)
        with patch('ColorAdminApp.modules.regional_routes.original_route_order',side_effect=lambda local,start:list(local)) as optimize:
            ordered = period_route_order(houses,origin,3,route_order=optimize)
        self.assertEqual(optimize.call_count,2)
        self.assertEqual({m['preferencia_periodo_visita'] for h in optimize.call_args_list[0].args[0] for m in h['members']},{'Manhã'})
        self.assertEqual({m['preferencia_periodo_visita'] for h in optimize.call_args_list[1].args[0] for m in h['members']},{'Tarde'})
        self.assertEqual(optimize.call_args_list[1].args[1],ordered[2][1]['coords'])

    def test_recalculation_preserves_the_selected_departure(self):
        plan = self.plan(group_count=1)
        plan['origins'] = {COMMONS[0]:(-23.54,-46.99), COMMONS[1]:(-23.54,-46.98)}
        plan['groups'][0]['origin_common'] = COMMONS[0]
        finalized = finalize_plan(plan)
        self.assertEqual(finalized['groups'][0]['origin_common'],COMMONS[0])
        self.assertEqual(finalized['groups'][0]['origin'],plan['origins'][COMMONS[0]])

    def test_period_aware_group_swaps_reduce_travel_and_preserve_quotas(self):
        from ColorAdminApp.modules.regional_routes import compact_period_groups, period_route_order
        from ColorAdminApp.utils.routing import haversine_distance
        origin = (-23.54,-46.98)
        houses = []
        for group in range(2):
            for index,(delta,period) in enumerate([(0.0001,'Manhã'),(.02,'Manhã'),(.0002,'Tarde'),(.0201,'Tarde')]):
                houses.append({'key':f'{group}-{index}','group_id':str(group),
                    'coords':(origin[0],origin[1]+delta+group*.00001), 'address':f'Rua {group}-{index}','bairro':'',
                    'members':[{'comum':COMMONS[0],'preferencia_periodo_visita':period}]})
        def total():
            distance=0
            for identity in ('0','1'):
                current=origin
                for _,house in period_route_order([h for h in houses if h['group_id']==identity],origin,2):
                    distance+=haversine_distance(current,house['coords'])
                    current=house['coords']
            return distance
        before=total()
        compact_period_groups(houses,teams(2),{COMMONS[0]:origin})
        self.assertLess(total(),before*.75)
        self.assertEqual(Counter(h['group_id'] for h in houses),{'0':4,'1':4})
        for identity in ('0','1'):
            self.assertEqual(Counter(h['members'][0]['preferencia_periodo_visita'] for h in houses if h['group_id']==identity),{'Manhã':2,'Tarde':2})

    def test_cross_period_swap_removes_far_morning_return_to_near_afternoon(self):
        from ColorAdminApp.modules.regional_routes import compact_period_groups, period_route_order
        from ColorAdminApp.utils.routing import haversine_distance
        origin = (-23.54,-46.98)
        specs = [('near-m',0,.0001,'Manhã'),('far-m',0,.0200,'Manhã'),
                 ('near-a',0,.0002,'Tarde'),('far-a',1,.0201,'Tarde'),
                 ('far-a2',1,.0202,'Tarde'),('far-m2',1,.0203,'Manhã')]
        houses = [{'key':key,'group_id':str(group),'coords':(origin[0],origin[1]+delta),
                   'address':key,'bairro':'','members':[{'comum':COMMONS[0],'preferencia_periodo_visita':period}]}
                  for key,group,delta,period in specs]
        def total():
            distance=0
            for identity in ('0','1'):
                current=origin
                for _,house in period_route_order([h for h in houses if h['group_id']==identity],origin,2):
                    distance+=haversine_distance(current,house['coords'])
                    current=house['coords']
            return distance
        before=total()
        preferences={h['key']:h['members'][0]['preferencia_periodo_visita'] for h in houses}
        compact_period_groups(houses,teams(2),{COMMONS[0]:origin})
        self.assertLess(total(),before*.85)
        self.assertEqual(Counter(h['group_id'] for h in houses),{'0':3,'1':3})
        self.assertEqual({h['key']:h['members'][0]['preferencia_periodo_visita'] for h in houses},preferences)
        for identity in ('0','1'):
            ordered=period_route_order([h for h in houses if h['group_id']==identity],origin,2)
            longitudes=[h['coords'][1] for _,h in ordered]
            self.assertEqual(longitudes,sorted(longitudes))

    def test_flexible_house_does_not_force_a_far_morning_detour(self):
        from ColorAdminApp.modules.regional_routes import period_route_order
        origin=(-23.54,-46.98)
        houses=[{'key':key,'coords':(origin[0],origin[1]+delta),'address':key,'bairro':'',
                 'members':[{'preferencia_periodo_visita':preference}]}
                for key,delta,preference in [('near',.0001,'Tarde'),('far',.02,'')]]
        ordered=period_route_order(houses,origin,1)
        self.assertEqual([(hour,h['key']) for hour,h in ordered],[(14,'near'),(14,'far')])

    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_planning_never_geocodes_addresses_or_reads_supabase(self, get):
        people=members();people[0]['endereco']='Rua sem GPS, 100'
        finalize_plan(self.plan(people=people))
        get.assert_not_called()

    def test_existing_fixed_times_are_not_overlapped(self):
        people=members(2)
        people.append({'id':'outside','nome':'Outra casa','comum':'OUTRA COMUM','endereco':'Rua fixa, 20'})
        agenda=[{'id':'fixed','irmandade_id':'outside','equipe_id':'0','status':'Marcada',
                 'data_inicio':DAY+'T09:05:00-03:00','data_fim':DAY+'T10:00:00-03:00'}]
        plan=finalize_plan(self.plan(group_count=1,people=people,agenda=agenda))
        self.assertTrue(all(h['start'][11:16]>='10:00' for h in plan['houses']))

    def test_future_visit_still_blocks_member_after_address_change(self):
        agenda=[{'id':'v','irmandade_id':'0','equipe_id':'0','status':'Marcada',
                 'data_inicio':'2099-10-20T09:00:00-03:00','endereco_visitado':'Rua antiga, 30'}]
        plan=self.plan(agenda=agenda)
        self.assertEqual(len(plan['houses']),6)

    def test_coordinate_outlier_does_not_direct_route_to_another_city(self):
        people=members(4);people[0]['endereco']='[-21.29, -50.34] Rua distante, 100'
        plan=self.plan(people=people)
        house=next(h for h in plan['houses'] if h['members'][0]['id']=='0')
        self.assertIsNone(house['coords'])

    @patch('requests.get')
    @patch('requests.post')
    def test_qr_is_generated_locally_with_the_destination_municipality(self,post,get):
        from ColorAdminApp.modules.regional_route_reports import prepare_navigation
        group=teams(1)[0]
        group['houses']=[{'address':'Rua da Familia, 10','bairro':'Vila das Chacaras','coords':None}]
        prepare_navigation([group],'ITAPEVI',RequestFactory().get('/'))
        self.assertTrue(group['houses'][0]['qr_data'].startswith('data:image/svg+xml;base64,'))
        self.assertIn('ITAPEVI',group['houses'][0]['navigation_url'])
        get.assert_not_called();post.assert_not_called()


class RegionalPlannerAccessTests(SimpleTestCase):
    @patch.object(views,'read')
    def test_registry_coordinator_does_not_confirm_attendance_automatically(self,read):
        read.side_effect=[
            [{'id':'a','nome':'Grupo A','ativo':True,'coordenador_nome':'Emerson Nunes Moraes','exige_confirmacao_data':True}],[],[]]
        group=views.daily_groups(DAY,'ITAPEVI')[0]
        self.assertEqual(group['coordenador_nome'],'Emerson Nunes Moraes')
        self.assertFalse(group['confirmado'])
        self.assertFalse(group['participacao_salva'])

    @patch.object(views,'read')
    def test_registry_seed_preserves_the_daily_substitute_and_confirmation(self,read):
        read.side_effect=[
            [{'id':'a','nome':'Grupo A','ativo':True,'coordenador_nome':'Emerson Nunes Moraes','exige_confirmacao_data':True}],
            [{'equipe_id':'a','confirmado':True,'coordenador_nome':'Sidney de Aguiar Fogaça','updated_at':'version'}],[]]
        group=views.daily_groups(DAY,'ITAPEVI')[0]
        self.assertTrue(group['confirmado'])
        self.assertEqual(group['coordenador_nome'],'Sidney de Aguiar Fogaça')
        self.assertEqual(group['coordenador_cadastrado'],'Emerson Nunes Moraes')

    def test_common_identity_preserves_scope_and_accepts_legacy_names(self):
        common = 'BR-22-3062 - JARDIM ALABAMA'
        rows = [
            {'id':'1','comum':'BR-22-3062 - Jardim Alabama'},
            {'id':'2','comum':'Nome antigo','codigo_comum':'BR-22-3062'},
            {'id':'3','comum':'BR-21-1542 - VILA BELMIRA'},
        ]
        normalized = views.canonical_members(rows,[common])
        self.assertEqual([m['id'] for m in normalized],['1','2'])
        self.assertEqual({m['comum'] for m in normalized},{common})
        self.assertEqual(rows[0]['comum'],'BR-22-3062 - Jardim Alabama')
        query = views.common_member_filter([common])['or']
        self.assertIn('comum.ilike.BR-22-3062*',query)
        self.assertIn('codigo_comum.in.("BR-22-3062")',query)

    def test_confirmation_preserves_original_registry_common_and_display_roundtrip(self):
        common = 'BR-22-3062 - JARDIM ALABAMA'
        people = members(2)
        for person in people:
            person['comum'] = 'BR-22-3062 - Jardim Alabama'
        normalized = views.canonical_members(people,[common])
        plan = finalize_plan(build_plan(normalized,[],teams(1),DAY,'ITAPEVI',[common]))
        payload = views.database_plan(plan)
        for house in payload['houses']:
            for member in house['members']:
                original = next(p for p in people if p['id']==member['id'])
                self.assertEqual(member['comum'],original['comum'])
                self.assertEqual(member['endereco'],original['endereco'])
            restored = views.canonical_members(house['members'],[common])
            self.assertEqual({m['comum'] for m in restored},{common})
            self.assertEqual({m['comum_cadastro'] for m in restored},{'BR-22-3062 - Jardim Alabama'})
        self.assertEqual({m['comum'] for h in plan['houses'] for m in h['members']},{common})

    @patch.object(views,'user_scope',return_value={'profile':{'role_id':3}})
    @patch.object(views,'location',return_value=(DAY,'ITAPEVI',[
        {'comum':'BR-21-1542 - VILA BELMIRA'}, {'comum':'BR-22-3062 - JARDIM ALABAMA'}]))
    @patch.object(views,'rpc',return_value='version')
    @patch.object(views,'daily_groups',return_value=[dict(t,participacao_salva=True) for t in teams(4)])
    @patch.object(views,'read')
    def test_alabama_case_difference_does_not_omit_selected_families(self,read,daily,rpc,location,scope):
        people = members(45)
        for i,person in enumerate(people):
            person['comum'] = 'BR-21-1542 - VILA BELMIRA' if i<21 else 'BR-22-3062 - Jardim Alabama'
        read.side_effect = [people,[],[]]
        plan,_,_ = views.sources(self.request({}),{'data':DAY,'municipio':'ITAPEVI',
            'comuns':['BR-21-1542 - VILA BELMIRA','BR-22-3062 - JARDIM ALABAMA']})
        self.assertEqual([c['included_records'] for c in plan['coverage']],[21,24])
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[11,11,11,12])
        self.assertIn('or',read.call_args_list[0].kwargs)

    def setUp(self):
        geometry=patch.object(views,'enrich_plan_geometry',side_effect=lambda plan:plan.setdefault('origins',{}) or plan)
        geometry.start();self.addCleanup(geometry.stop)
        roads=patch.object(views,'enrich_road_distances',side_effect=lambda plan:plan)
        roads.start();self.addCleanup(roads.stop)
        self.factory=RequestFactory()
        self.actor=str(uuid4())

    def request(self,payload,actor=None):
        req=self.factory.post('/',data=json.dumps(payload),content_type='application/json')
        req.session={'authenticated':True,'user_id':actor or self.actor}
        return req

    @patch.object(views,'read')
    def test_day_indicators_count_addresses_without_double_counting_residents(self,read):
        read.return_value=[
            {'id':'v1','irmandade_id':'m1','equipe_id':'a','endereco_visitado':'Rua A, 10','status':'Marcada'},
            {'id':'v2','irmandade_id':'m2','equipe_id':'a','endereco_visitado':'Rua A, 10','status':'Marcada'},
            {'id':'v3','irmandade_id':'m3','equipe_id':'b','endereco_visitado':'Rua B, 20','status':'Realizada'},
            {'id':'v4','irmandade_id':'m4','equipe_id':'b','endereco_visitado':'Rua C, 30','status':'Cancelada'},
        ]
        result=views.day_agenda_summary(DAY,'ITAPEVI',[{'id':'a'},{'id':'b'}])
        self.assertEqual(result,{'families':2,'groups':2})
        self.assertEqual(read.call_args.kwargs['roteiro_regional_id'],'not.is.null')
        self.assertNotIn('nome',read.call_args.kwargs['select'])
        self.assertIn('equipe_id',read.call_args.kwargs)

    @patch.object(views,'day_agenda_summary',side_effect=requests.Timeout())
    def test_indicator_failure_does_not_invalidate_a_successful_operation(self,summary):
        self.assertIsNone(views.safe_day_summary(DAY,'ITAPEVI'))

    @patch.object(views,'read')
    def test_registered_team_coordinator_overrides_legacy_member_badge(self,read):
        read.side_effect=[[{'id':'a','nome':'Grupo A','ativo':True,'coordenador_nome':'Manoel'}],[],
                          [{'id':'m','nome':'Emerson','grupo_regional_id':'a','cargo_outros':'Coordenador','status':'Ativo'}]]
        group=views.daily_groups(DAY,'ITAPEVI')[0]
        self.assertEqual(group['coordenador_cadastrado'],'Manoel')
        self.assertEqual(group['coordenador_nome'],'Manoel')
        self.assertTrue(group['cadastro_disponivel'])

    @patch.object(views,'read')
    def test_rf_and_re_keep_their_independent_calendar(self,read):
        read.side_effect=[
            [{'id':'a','nome':'Grupo A','ativo':True},{'id':'rf','nome':'Grupo RF','ativo':True},{'id':'re','nome':'Grupo RE','ativo':True}],
            [{'equipe_id':'a','confirmado':True,'coordenador_nome':'Manoel'}],
            [],
        ]
        result=views.daily_groups(DAY,'ITAPEVI')
        self.assertEqual([g['nome'] for g in result],['Grupo A'])
        self.assertEqual(result[0]['coordenador_nome'],'Manoel')

    @patch.object(views,'read')
    def test_registered_coordinator_prefills_without_silently_saving_attendance(self,read):
        read.side_effect=[
            [{'id':'a','nome':'Grupo A','ativo':True}],[],
            [{'id':'m','nome':'Emerson','grupo_regional_id':'a','cargo_outros':'Coordenador','status':'Ativo','equipe_id':'local'},
             {'id':'n','nome':'Participante','grupo_regional_id':'a','cargo_outros':'','status':'Ativo','equipe_id':None}],
        ]
        group=views.daily_groups(DAY,'ITAPEVI')[0]
        self.assertEqual(group['coordenador_nome'],'Emerson')
        self.assertTrue(group['confirmado'])
        self.assertFalse(group['participacao_salva'])
        self.assertIn('grupo_regional_id',read.call_args.kwargs)

    @patch.object(views,'read')
    def test_date_override_preserves_disabled_group_and_registered_coordinator(self,read):
        read.side_effect=[
            [{'id':'a','nome':'Grupo A','ativo':True}],
            [{'equipe_id':'a','confirmado':False,'coordenador_nome':'Manoel','updated_at':'version'}],
            [{'id':'m','nome':'Emerson','grupo_regional_id':'a','cargo_outros':'Coordenador','status':'Ativo'}],
        ]
        group=views.daily_groups(DAY,'ITAPEVI')[0]
        self.assertEqual(group['coordenador_nome'],'Manoel')
        self.assertEqual(group['coordenador_cadastrado'],'Emerson')
        self.assertFalse(group['confirmado'])
        self.assertTrue(group['participacao_salva'])

    @patch.object(views,'location',return_value=(DAY,'ITAPEVI',[{'comum':c} for c in COMMONS]))
    @patch.object(views,'rpc',return_value='version')
    @patch.object(views,'daily_groups',return_value=[dict(t,participacao_salva=True) for t in teams(4)])
    @patch.object(views,'read')
    def test_legacy_client_capacity_is_ignored_and_all_families_are_included(self,read,daily,rpc,location):
        read.side_effect=[members(100),[],[]]
        plan,_,_=views.sources(self.request({}),{'data':DAY,'municipio':'ITAPEVI','comuns':COMMONS,'capacidade':8})
        self.assertEqual(len(plan['houses']),100)
        self.assertEqual(sorted(Counter(h['group_id'] for h in plan['houses']).values()),[25]*4)

    @patch.object(views,'user_scope',return_value={'level':'local'})
    @patch.object(views,'read')
    def test_local_profiles_cannot_read_or_change_regional_plans(self,read,scope):
        self.assertEqual(views.api(self.request({'action':'preview'})).status_code,403)
        read.assert_not_called()

    @patch.object(views,'user_scope',return_value={'level':'municipal'})
    @patch.object(views,'visible_commons',return_value=[{'comum':COMMONS[0],'cidade':'ITAPEVI'}])
    @patch.object(views,'rpc')
    def test_another_municipality_is_rejected_before_database_access(self,rpc,catalog,scope):
        req=self.request({'action':'preview','data':DAY,'municipio':'JANDIRA','comuns':COMMONS})
        self.assertEqual(views.api(req).status_code,403)
        rpc.assert_not_called()

    @patch.object(views,'allowed',return_value=True)
    @patch.object(views,'location',return_value=(DAY,'ITAPEVI',[{'comum':c} for c in COMMONS]))
    @patch.object(views,'read',return_value=[])
    @patch.object(views,'sources')
    @patch.object(views,'rpc')
    def test_stale_preview_never_writes_agenda(self,rpc,sources,read,location,allowed):
        token=signing.dumps({'actor':self.actor,'id':str(uuid4()),'options':{},'fingerprint':'old','version':'old'},salt=views.SALT)
        sources.return_value=({},'new','new')
        response=views.api(self.request({'action':'confirm','token':token}))
        self.assertEqual(response.status_code,409)
        rpc.assert_not_called()

    @patch.object(views,'allowed',return_value=True)
    @patch.object(views,'read')
    def test_preview_cannot_be_used_by_another_user(self,read,allowed):
        token=signing.dumps({'actor':str(uuid4()),'options':{}},salt=views.SALT)
        self.assertEqual(views.api(self.request({'action':'confirm','token':token})).status_code,403)
        read.assert_not_called()

    @patch.object(views,'allowed',return_value=True)
    @patch.object(views,'sources')
    def test_preview_returns_a_signed_token_without_graving_agenda(self,sources,allowed):
        sources.return_value=(build_plan(members(),[],teams(),DAY,'ITAPEVI',COMMONS),'version','fingerprint')
        response=views.api(self.request({'action':'preview','data':DAY,'municipio':'ITAPEVI','comuns':COMMONS}))
        self.assertEqual(response.status_code,200)
        result=json.loads(response.content)
        self.assertEqual(len(result['plan']['houses']),7)
        self.assertEqual(signing.loads(result['token'],salt=views.SALT)['actor'],self.actor)

    @patch('ColorAdminApp.views.render',side_effect=lambda req,template,context:context)
    @patch('ColorAdminApp.views.user_scope',return_value={'level':'global'})
    @patch('ColorAdminApp.views.visible_commons',return_value=[{'comum':'COMUM','cidade':'ITAPEVI'}])
    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.utils.routing.auto_dispatch_visits')
    @patch('ColorAdminApp.utils.routing.get_common_coordinates',return_value=None)
    def test_legacy_regional_print_does_not_top_up_a_balanced_group(self,origin,dispatch,get,catalog,scope,render):
        from unittest.mock import Mock
        from ColorAdminApp.views import visitasRoteiro
        get.return_value=Mock(json=lambda:[])
        req=self.factory.get('/visitas/roteiro/',{'comum':'COMUM','data':DAY,'equipe':'Grupo A','casas':'10'})
        context=visitasRoteiro(req)
        self.assertEqual(context['roteiro'],[])
        dispatch.assert_not_called()


class RegionalRouteExportsTests(SimpleTestCase):
    def setUp(self):
        geometry=patch.object(views,'enrich_plan_geometry',side_effect=lambda plan:plan)
        geometry.start();self.addCleanup(geometry.stop)
        from .regional_route_fixtures import offline_map_data
        maps=patch('ColorAdminApp.modules.regional_route_map.google_route_map',side_effect=offline_map_data)
        maps.start();self.addCleanup(maps.stop)
        self.factory=RequestFactory()
        self.plan=finalize_plan(build_plan(members(12),[],teams(2),DAY,'ITAPEVI',COMMONS))
        self.plan['issued_at']='17/11/2026 14:20'
        self.identity=uuid4()

    def output(self,role=1,**params):
        req=self.factory.get('/',params)
        req.session={'authenticated':True,'user_id':str(uuid4()),'user_profile':{'full_name':'Operador de teste'}}
        def records(table,**kwargs):
            if table=='visitas_roteiros_regionais':return [{'plano':deepcopy(self.plan)}]
            return [{'id':m['id'],'comum':m['comum'],'preferencia_periodo_visita':m.get('preferencia_periodo_visita')} for h in self.plan['houses'] for m in h['members']]
        with patch.object(views,'allowed',return_value=True),patch.object(views,'read',side_effect=records),patch.object(views,'rpc',return_value={'agendamentos':12,'protegidos':0,'version':'delete-version'}),patch.object(views,'location',return_value=(DAY,'ITAPEVI',[{'comum':c} for c in COMMONS])),patch.object(views,'user_scope',return_value={'profile':{'role_id':role}}):
            return views.print_plan(req,self.identity)

    def test_manifest_exposes_individual_files_without_changing_agenda(self):
        result=json.loads(self.output(formato='manifesto').content)
        self.assertEqual(len(result['groups']),2)
        self.assertEqual([g['families'] for g in result['groups']],[6,6])
        self.assertTrue(result['groups'][1]['filename'].endswith('_GRUPO_B.pdf'))
        self.assertIn('grupo=1',result['groups'][1]['pdf_url'])

    def test_individual_preview_reuses_original_template(self):
        response=self.output(grupo='0',mapa='none')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'class="visit-card"',response.content)
        self.assertIn('Coordenador 0',response.content.decode())

    def test_individual_pdf_preserves_names_header_and_only_selected_group(self):
        from pypdf import PdfReader
        response=self.output(formato='pdf',grupo='1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'],'application/pdf')
        reader=PdfReader(io.BytesIO(response.content))
        text='\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('CONGREGAÇÃO CRISTÃ NO BRASIL',text)
        self.assertIn('Coordenador 1',text)
        self.assertIn('Grupo de Visitas Regional',text)
        self.assertNotIn('Secretaria Regional da Música',text)
        self.assertNotIn('Coordenador 0',text)
        self.assertIn('Impresso por:',text)
        self.assertIn('Comum do cadastro:',text)
        self.assertIn('GRUPO_B.pdf',response['Content-Disposition'])

    def test_zip_contains_one_real_pdf_per_group(self):
        from pypdf import PdfReader
        response=self.output(formato='zip')
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(len(archive.namelist()),2)
            for name in archive.namelist():
                self.assertTrue(name.startswith('ROTEIRO_VISITAS_'))
                self.assertTrue(PdfReader(io.BytesIO(archive.read(name))).pages)

    def test_pdf_and_zip_work_without_static_in_python_bundle(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from reportlab.pdfbase.ttfonts import TTFont
        from ColorAdminApp.modules import regional_route_pdf_components as components
        # Force font loading even when another export already registered it.
        with TemporaryDirectory() as base, self.settings(BASE_DIR=Path(base)), \
                patch.object(components.pdfmetrics,'getRegisteredFontNames',return_value=[]), \
                patch.object(components,'TTFont',wraps=TTFont) as load_font:
            self.assertFalse((Path(base)/'static').exists())
            for params in ({'formato':'pdf','grupo':'1'},{'formato':'zip'}):
                response=self.output(**params)
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.content)
            self.assertTrue(load_font.called)
            self.assertTrue(Path(load_font.call_args.args[1]).is_file())

    def test_excel_uses_real_dates_and_fills_entire_report_width(self):
        from openpyxl import load_workbook
        response=self.output(formato='excel')
        book=load_workbook(io.BytesIO(response.content));sheet=book.active
        self.assertEqual(sheet.max_row,17)
        self.assertEqual(sheet['H6'].number_format,'dd/mm/yyyy')
        self.assertEqual(sheet['H6'].value.date().isoformat(),DAY)
        self.assertEqual(sheet.freeze_panes,'A6')
        self.assertEqual(sheet.auto_filter.ref,'A5:K17')

    def test_invalid_group_is_rejected_instead_of_exporting_every_group(self):
        self.assertEqual(self.output(formato='pdf',grupo='unknown').status_code,404)
        self.assertEqual(self.output(formato='pdf').status_code,400)

    def test_deleted_distribution_cannot_be_exported(self):
        self.plan['deleted_at']='2026-11-17T12:00:00-03:00'
        self.assertEqual(self.output(formato='manifesto').status_code,410)
        self.assertEqual(self.output(formato='pdf',grupo='0').status_code,410)

    def test_restricted_notes_in_saved_snapshot_follow_exporting_user_role(self):
        from pypdf import PdfReader
        for house in self.plan['houses']:
            house['members'][0]['apontamentos_restritos']='Nota restrita de validacao'
        for role,expected in [(1,True),(4,False)]:
            result=self.output(role=role,formato='pdf',grupo='0')
            text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(result.content)).pages)
            self.assertEqual('Nota restrita de validacao' in text,expected)

    @patch.object(views,'allowed',return_value=True)
    @patch.object(views,'daily_groups',return_value=teams(2))
    @patch.object(views,'location',return_value=(DAY,'ITAPEVI',[{'comum':c} for c in COMMONS]))
    @patch.object(views,'read',side_effect=requests.Timeout())
    @patch.object(views,'visible_commons',return_value=[])
    @patch.object(views,'user_scope',return_value={'level':'global'})
    def test_history_failure_does_not_block_coordinators(self,*mocks):
        req=self.factory.get('/',{'data':DAY,'municipio':'ITAPEVI'})
        req.session={'user_id':str(uuid4())}
        response=views.api(req)
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(json.loads(response.content)['groups']),2)
        self.assertTrue(json.loads(response.content)['warning'])


class RegionalCoordinatorSearchTests(SimpleTestCase):
    @patch.object(views,'read')
    @patch.object(views,'rpc')
    def test_titular_labels_come_from_permanent_roles_without_writing_assignments(self,rpc,read):
        people=[{'id':'alan','nome':'Alan Henrique Fernandes de Oliveira','municipio':'ITAPEVI','ativo':True},
                {'id':'sergio','nome':'Sérgio Henrique de Melo','municipio':'ITAPEVI','ativo':True},
                {'id':'laudelino','nome':'Laudelino Guimarães Lima Júnior','municipio':'ITAPEVI','ativo':True}]
        read.side_effect=[people,[{'municipio':'ITAPEVI','equipe_id':'C','integrante_id':'alan'},
                                 {'municipio':'ITAPEVI','equipe_id':'D','integrante_id':'sergio'}]]
        req=self.factory.get('/',{'action':'integrants','data':DAY,'municipio':'ITAPEVI'});req.session={'user_id':self.actor}
        response=views.api(req)
        self.assertEqual(response.status_code,200)
        self.assertEqual(json.loads(response.content)['titulares'],{'C':people[0]['nome'],'D':people[1]['nome']})
        rpc.assert_not_called()

    def setUp(self):
        self.factory=RequestFactory()
        self.actor=str(uuid4())
        self.people=[{'id':'person-1','nome':'Laudelino Guimarães Lima Júnior','municipio':'ITAPEVI','ativo':True,'ministerio':'Ancião','comum_origem':'JD Paulista'}]
        for p in [patch.object(views,'allowed',return_value=True),patch.object(views,'location',return_value=(DAY,'ITAPEVI',[])),patch('ColorAdminApp.views.log_audit')]:
            p.start();self.addCleanup(p.stop)

    def post(self,groups):
        req=self.factory.post('/',data=json.dumps({'action':'participation','data':DAY,'municipio':'ITAPEVI','groups':groups}),content_type='application/json')
        req.session={'user_id':self.actor};return req

    @patch.object(views,'read')
    def test_search_returns_only_active_integrants_from_selected_municipality(self,read):
        read.return_value=self.people+[dict(self.people[0],id='outside',municipio='JANDIRA'),dict(self.people[0],id='inactive',ativo=False)]
        req=self.factory.get('/',{'action':'integrants','data':DAY,'municipio':'ITAPEVI'});req.session={'user_id':self.actor}
        response=views.api(req)
        self.assertEqual(response.status_code,200)
        self.assertEqual(json.loads(response.content)['integrantes'],self.people)
        self.assertEqual(read.call_args.kwargs['municipio'],'eq.ITAPEVI')

    @patch.object(views,'daily_groups',return_value=teams(2))
    @patch.object(views,'regional_integrants')
    @patch.object(views,'rpc')
    def test_selected_substitute_is_verified_and_never_changes_the_default_coordinator(self,rpc,registry,daily):
        registry.return_value=self.people
        supplied=[dict(t,atualizar_cadastro=True) for t in teams(2)]
        supplied[0].update(coordenador_integrante_id='person-1',coordenador_nome='Nome forjado')
        response=views.api(self.post(supplied))
        self.assertEqual(response.status_code,200)
        payload=rpc.call_args.kwargs['p_grupos']
        self.assertEqual(payload[0]['coordenador_nome'],self.people[0]['nome'])
        self.assertTrue(all(g['atualizar_cadastro'] is False for g in payload))

    @patch.object(views,'daily_groups',return_value=teams(2))
    @patch.object(views,'regional_integrants')
    @patch.object(views,'rpc')
    def test_unknown_person_and_duplicate_daily_assignment_are_rejected(self,rpc,registry,daily):
        registry.return_value=self.people
        supplied=teams(2);supplied[0]['coordenador_integrante_id']='outside'
        self.assertEqual(views.api(self.post(supplied)).status_code,403)
        supplied=teams(2)
        for group in supplied:group['coordenador_integrante_id']='person-1'
        self.assertEqual(views.api(self.post(supplied)).status_code,400)
        rpc.assert_not_called()


class RegionalRouteDeletionTests(SimpleTestCase):
    def setUp(self):
        self.actor=str(uuid4());self.identity=str(uuid4());self.factory=RequestFactory()
        for patcher in [patch.object(views,'allowed',return_value=True),
                        patch.object(views,'location',return_value=(DAY,'ITAPEVI',[{'comum':c} for c in COMMONS])),
                        patch('ColorAdminApp.views.log_audit')]:
            patcher.start();self.addCleanup(patcher.stop)

    def request(self,token,**options):
        req=self.factory.post('/',data=json.dumps({'action':'delete','token':token,**options}),content_type='application/json')
        req.session={'user_id':self.actor,'authenticated':True};return req

    def token(self,actor=None):
        return signing.dumps({'actor':actor or self.actor,'id':self.identity,'data':DAY,'municipio':'ITAPEVI','version':'v1'},salt=views.DELETE_SALT)

    def removal_token(self,actor=None):
        return signing.dumps({'actor':actor or self.actor,'id':self.identity,'data':DAY,'municipio':'ITAPEVI','version':'v1'},salt=views.REMOVE_SALT)

    @patch.object(views,'read')
    @patch.object(views,'rpc',return_value={'deleted':2,'removed_commons':[COMMONS[0]],'remaining_commons':[COMMONS[1]]})
    def test_partial_removal_sends_only_explicit_calendar_choices(self,rpc,read):
        read.return_value=[{'id':self.identity,'comuns':COMMONS}]
        response=views.api(self.request(self.removal_token(),action='remove_commons',comuns=[COMMONS[0]],agenda_comuns=[COMMONS[0]]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(rpc.call_args.kwargs['p_comuns'],[COMMONS[0]])
        self.assertEqual(rpc.call_args.kwargs['p_agenda_comuns'],[COMMONS[0]])
        self.assertEqual(json.loads(response.content)['remaining_commons'],[COMMONS[1]])

    @patch.object(views,'read')
    @patch.object(views,'rpc',return_value={'deleted':0,'removed_commons':[COMMONS[0]],'remaining_commons':[COMMONS[1]]})
    def test_remove_from_route_can_preserve_all_calendar_records(self,rpc,read):
        read.return_value=[{'id':self.identity,'comuns':COMMONS}]
        response=views.api(self.request(self.removal_token(),action='remove_commons',comuns=[COMMONS[0]],agenda_comuns=[]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(rpc.call_args.kwargs['p_agenda_comuns'],[])

    @patch.object(views,'read')
    @patch.object(views,'rpc')
    def test_calendar_cleanup_cannot_include_unselected_or_outside_commons(self,rpc,read):
        read.return_value=[{'id':self.identity,'comuns':COMMONS}]
        for selected,cleanup in [([COMMONS[0]],[COMMONS[1]]),(['OUTRA COMUM'],[]),([],[]),([COMMONS[0],COMMONS[0]],[]),([COMMONS[0]],None)]:
            response=views.api(self.request(self.removal_token(),action='remove_commons',comuns=selected,agenda_comuns=cleanup))
            self.assertEqual(response.status_code,400)
        rpc.assert_not_called()

    @patch.object(views,'read')
    @patch.object(views,'rpc')
    def test_partial_removal_cannot_use_another_actors_token(self,rpc,read):
        response=views.api(self.request(self.removal_token(str(uuid4())),action='remove_commons',comuns=[COMMONS[0]],agenda_comuns=[]))
        self.assertEqual(response.status_code,403)
        rpc.assert_not_called();read.assert_not_called()

    @patch.object(views,'read')
    @patch.object(views,'rpc',return_value=4)
    def test_signed_deletion_only_targets_selected_distribution(self,rpc,read):
        read.return_value=[{'id':self.identity,'comuns':COMMONS}]
        response=views.api(self.request(self.token()))
        self.assertEqual(response.status_code,200)
        self.assertEqual(json.loads(response.content)['deleted'],4)
        self.assertEqual(rpc.call_args.kwargs['p_id'],self.identity)
        self.assertEqual(rpc.call_args.kwargs['p_expected_version'],'v1')

    @patch.object(views,'read')
    @patch.object(views,'rpc')
    def test_another_operator_cannot_use_deletion_token(self,rpc,read):
        self.assertEqual(views.api(self.request(self.token(str(uuid4())))).status_code,403)
        read.assert_not_called();rpc.assert_not_called()

    @patch.object(views,'read',return_value=[{'comuns':['OUTRA COMUM']}])
    @patch.object(views,'rpc')
    def test_distribution_outside_scope_is_rejected(self,rpc,read):
        self.assertEqual(views.api(self.request(self.token())).status_code,403)
        rpc.assert_not_called()

    @patch.object(views,'rpc')
    def test_modified_confirmation_cannot_delete(self,rpc):
        self.assertEqual(views.api(self.request('invalid')).status_code,409)
        rpc.assert_not_called()

    @patch.object(views,'read')
    @patch.object(views,'rpc')
    def test_old_preview_cannot_recreate_deleted_distribution(self,rpc,read):
        read.return_value=[{'id':self.identity,'criado_por':self.actor,'comuns':COMMONS,'deleted_at':'2026-11-17T12:00:00-03:00'}]
        token=signing.dumps({'actor':self.actor,'id':self.identity,'options':{'data':DAY,'municipio':'ITAPEVI'}},salt=views.SALT)
        req=self.factory.post('/',data=json.dumps({'action':'confirm','token':token}),content_type='application/json')
        req.session={'user_id':self.actor,'authenticated':True}
        self.assertEqual(views.api(req).status_code,409)
        rpc.assert_not_called()
