from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase

from ColorAdminApp.modules import regional_route_geometry as geo
from ColorAdminApp.modules.regional_route_reports import decorate_groups
from ColorAdminApp.modules.regional_routes import build_plan,finalize_plan,compact_balanced_groups
from .tests_regional_routes import members,teams,COMMONS,DAY


class RegionalGeometryTests(SimpleTestCase):
    def setUp(self):
        cache=LocMemCache(str(uuid4()),{})
        patcher=patch.object(geo,'cache',cache);patcher.start();self.addCleanup(patcher.stop)

    @patch.object(geo,'geocode_address_fallback',return_value=(-23.54,-46.98))
    def test_repeated_address_uses_disk_cache_interface_instead_of_provider(self,provider):
        first=geo.cached_coordinates('Rua A, 10','ITAPEVI','Centro')
        self.assertEqual(first,geo.cached_coordinates('Rua A, 10','ITAPEVI','Centro'))
        provider.assert_called_once()

    @patch.object(geo,'get_common_coordinates',return_value=(-23.54,-46.98))
    @patch.object(geo,'geocode_address_fallback',return_value=None)
    def test_missing_location_keeps_house_and_negative_cache(self,provider,origin):
        plan=finalize_plan(build_plan(members(1),[],teams(1),DAY,'ITAPEVI',COMMONS))
        plan['houses'][0]['coords']=None
        geo.enrich_plan_geometry(plan);geo.enrich_plan_geometry(plan)
        self.assertEqual(len(plan['houses']),1)
        self.assertEqual(plan['without_coordinates'],1)
        provider.assert_called_once()

    def test_first_distance_starts_at_common_and_second_at_previous_house(self):
        plan=finalize_plan(build_plan(members(2),[],teams(1),DAY,'ITAPEVI',COMMONS))
        group={**plan['groups'][0],'houses':plan['houses'],'origins':{COMMONS[0]:[-23.54,-46.981]}}
        decorate_groups([group])
        self.assertIn('da congregação',group['houses'][0]['distance_label'])
        self.assertIn('do último ponto',group['houses'][1]['distance_label'])
        self.assertGreater(group['houses'][0]['distance_meters'],group['houses'][1]['distance_meters'])
        group['houses'][0]['coords']=None
        decorate_groups([group])
        self.assertNotIn('distance_meters',group['houses'][1])
        self.assertIn('indisponível',group['houses'][1]['distance_label'])

    def test_group_order_starts_nearest_its_common_without_changing_allocation(self):
        plan=build_plan(members(3),[],teams(1),DAY,'ITAPEVI',COMMONS)
        plan['origins']={COMMONS[0]:[-23.54,-46.9798]}
        ids={m['id'] for h in plan['houses'] for m in h['members']}
        finalize_plan(plan)
        first=next(h for h in plan['houses'] if h['number']==1)
        self.assertEqual(first['members'][0]['id'],'2')
        self.assertEqual(ids,{m['id'] for h in plan['houses'] for m in h['members']})

    def test_departure_cannot_remain_in_another_common_after_swaps(self):
        people=members(3)
        for person in people:person['comum']=COMMONS[1]
        plan=build_plan(people,[],teams(1),DAY,'ITAPEVI',COMMONS)
        plan['origins']={COMMONS[0]:[-23.54,-46.981],COMMONS[1]:[-23.54,-46.98]}
        plan['groups'][0].update(origin_common=COMMONS[0],origin=plan['origins'][COMMONS[0]])
        finalize_plan(plan)
        self.assertEqual(plan['groups'][0]['origin_common'],COMMONS[1])
        self.assertEqual(plan['groups'][0]['origin'],plan['origins'][COMMONS[1]])

    @patch('ColorAdminApp.utils.routing.geocode_address_fallback',return_value=(-23.515248,-46.9859838))
    def test_vila_das_chacaras_uses_the_provided_church_address(self,provider):
        from ColorAdminApp.utils.routing import get_common_coordinates
        get_common_coordinates.cache_clear()
        self.addCleanup(get_common_coordinates.cache_clear)
        result=get_common_coordinates('BR-22-2999 - VILA DAS CHÁCARAS','ITAPEVI')
        self.assertEqual(result,(-23.515248,-46.9859838))
        provider.assert_called_once_with('Rua Rivadália, 360',city='ITAPEVI')

    @patch.object(geo,'get_common_coordinates',return_value=(-23.515248,-46.9859838))
    def test_church_address_change_avoids_previous_name_only_negative_cache(self,provider):
        import hashlib
        common='BR-22-2999 - VILA DAS CHÁCARAS'
        old_key=hashlib.sha256(repr((geo.normalize_text(common),'ITAPEVI','',True)).encode()).hexdigest()
        geo.cache.set(old_key,{'coords':None},timeout=3600)
        self.assertEqual(geo.cached_coordinates(common,'ITAPEVI',common=True),[-23.515248,-46.9859838])
        provider.assert_called_once()

    def test_unknown_correct_church_does_not_borrow_other_church_distance(self):
        people=members(2)
        for person in people:person['comum']=COMMONS[1]
        plan=build_plan(people,[],teams(1),DAY,'ITAPEVI',COMMONS)
        origins={COMMONS[0]:[-23.54,-46.981],COMMONS[1]:None}
        plan['origins']=origins
        plan['groups'][0].update(origin_common=COMMONS[0],origin=origins[COMMONS[0]])
        finalize_plan(plan)
        self.assertEqual(plan['groups'][0]['origin_common'],COMMONS[1])
        self.assertIsNone(plan['groups'][0]['origin'])
        # O mesmo cuidado vale para PDFs de snapshots antigos ja salvos.
        group={**plan['groups'][0],'houses':plan['houses'],'origins':origins,
               'origin_common':COMMONS[0],'origin':origins[COMMONS[0]]}
        decorate_groups([group])
        self.assertEqual(group['origin_common'],COMMONS[1])
        self.assertIsNone(group['origin'])
        self.assertNotIn('distance_meters',group['houses'][0])
        self.assertIn('indisponível',group['houses'][0]['distance_label'])
        self.assertIn('distance_meters',group['houses'][1])

    @patch.object(geo,'cached_coordinates',return_value=[-23.54,-46.98])
    def test_null_origin_in_saved_snapshot_can_be_resolved_again(self,provider):
        plan={'commons':[COMMONS[1]],'city':'ITAPEVI','origins':{COMMONS[1]:None},'houses':[]}
        geo.enrich_plan_geometry(plan)
        self.assertEqual(plan['origins'][COMMONS[1]],[-23.54,-46.98])
        provider.assert_called_once_with(COMMONS[1],'ITAPEVI',common=True)

    def test_distance_chain_does_not_return_to_church_in_afternoon(self):
        from ColorAdminApp.utils.routing import haversine_distance
        plan=finalize_plan(build_plan(members(3),[],teams(1),DAY,'ITAPEVI',COMMONS))
        group={**plan['groups'][0],'houses':sorted(plan['houses'],key=lambda h:h['number']),
               'origins':{COMMONS[0]:[-23.54,-46.981]}}
        group['houses'][2]['start']=DAY+'T14:00:00-03:00'
        decorate_groups([group])
        houses=group['houses']
        for index in (1,2):
            self.assertAlmostEqual(houses[index]['distance_meters'],haversine_distance(houses[index-1]['coords'],houses[index]['coords']))
            self.assertNotAlmostEqual(houses[index]['distance_meters'],haversine_distance(group['origin'],houses[index]['coords']))

    def test_geographic_swaps_reduce_spread_without_changing_group_counts(self):
        from collections import Counter
        from ColorAdminApp.utils.routing import haversine_distance
        houses=[{'key':str(i),'group_id':group,'coords':[-23.54,lng]} for i,(group,lng) in enumerate([
            ('A',-46.98),('A',-46.97),('B',-46.9801),('B',-46.9701)])]
        before=Counter(h['group_id'] for h in houses)
        compact_balanced_groups(houses)
        self.assertEqual(before,Counter(h['group_id'] for h in houses))
        for group in before:
            local=[h for h in houses if h['group_id']==group]
            self.assertLess(haversine_distance(local[0]['coords'],local[1]['coords']),30)

    def test_missing_preference_is_explicit_and_registered_preference_is_preserved(self):
        plan=finalize_plan(build_plan(members(2),[],teams(1),DAY,'ITAPEVI',COMMONS))
        group={**plan['groups'][0],'houses':plan['houses']}
        decorate_groups([group])
        self.assertEqual(group['houses'][0]['preference_label'],'Sem preferência informada')
        group['houses'][0]['members'][0]['preferencia_periodo_visita']='Manhã'
        decorate_groups([group])
        self.assertEqual(group['houses'][0]['preference_label'],'Prefere manhã')
