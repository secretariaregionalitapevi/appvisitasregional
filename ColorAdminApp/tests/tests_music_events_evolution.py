from django.test import SimpleTestCase
from ColorAdminApp.modules.music_events_evolution import comparison, evolution


class EvolutionTests(SimpleTestCase):
    def fixture(self):
        events=[{'id':'a','titulo':'Anterior','tipo':'ENSAIO_REGIONAL','familia':'GERAL','status':'ABERTO','data_evento':'2026-05-17'},
                {'id':'b','titulo':'Atual','tipo':'ENSAIO_REGIONAL','familia':'GERAL','status':'ABERTO','data_evento':'2026-09-20'},
                {'id':'c','titulo':'RT','tipo':'REUNIAO_TECNICA','familia':'CORDAS','status':'ABERTO','data_evento':'2026-08-29'}]
        sites=[{'id':e['id']+'-local','evento_id':e['id'],'nome':'ITAPEVI'} for e in events]
        rows=[]
        for event,count in [('a',4),('b',2),('c',6)]:
            for i in range(count):rows.append({'evento_id':event,'local_id':event+'-local','categoria':'MUSICO',
                'municipio_informado':'ITAPEVI','comum_informada':'Comum de teste','situacao':'PRESENTE','familia':'CORDAS'})
        return events,rows,sites

    def test_selected_event_compares_same_type_not_rt(self):
        e,r,l=self.fixture();data=evolution(e,r,l,{'evento':'b'})
        self.assertEqual(len(data['points']),2)
        self.assertEqual(data['metrics']['musicians']['change'],-50)
        self.assertEqual(data['series'][0]['summary']['from_peak'],-50)

    def test_history_includes_instructors_and_candidates_without_double_counting(self):
        e,r,l=self.fixture()
        r[0]['cargo']='INSTRUTORA'
        r[0]['nivel']='CANDIDATA'
        r[4]['cargo']='INSTRUTOR'
        r[4]['nivel']='CANDIDATO(A)'
        data=evolution(e,r,l,{'evento':'b'})
        city=next(x for x in data['municipalities'] if x['name']=='ITAPEVI')
        self.assertEqual([p['instructors'] for p in city['points']],[0,1])
        self.assertEqual([p['instructresses'] for p in city['points']],[1,0])
        self.assertEqual([p['candidates'] for p in city['points']],[1,1])
        self.assertEqual([p['musicians'] for p in city['points']],[4,2])

    def test_location_identity_is_resolved_across_events(self):
        e,r,l=self.fixture();data=evolution(e,r,l,{'evento':'b','local':'b-local'})
        self.assertEqual([p['total'] for p in data['points']],[4,2])

    def test_single_event_does_not_invent_growth_or_decline(self):
        e,r,l=self.fixture();data=evolution(e,r,l,{'evento':'a'})
        self.assertEqual(len(data['points']),1)
        self.assertIsNone(data['metrics']['total']['change'])
        self.assertIsNone(data['series'][0]['summary']['from_peak'])

    def test_origin_filter_applies_to_every_historical_point(self):
        e,r,l=self.fixture();data=evolution(e,r,l,{'evento':'b','municipios':['COTIA']})
        self.assertTrue(all(p['total']==0 for p in data['points']))

    def test_previous_zero_has_no_infinite_percentage(self):
        c=comparison([{'total':0},{'total':3}],'total')
        self.assertEqual(c['latest'],3)
        self.assertIsNone(c['change'])

    def test_municipal_history_uses_origin_and_never_invents_missing_points(self):
        e,r,l=self.fixture()
        r.append(dict(r[0],evento_id='b',local_id='b-local',municipio_informado='PIRAPORA DO BOM JESUS'))
        data=evolution(e,r,l,{'evento':'b'})
        itapevi=next(x for x in data['municipalities'] if x['name']=='ITAPEVI')
        cotia=next(x for x in data['municipalities'] if x['name']=='PIRAPORA DO BOM JESUS')
        self.assertEqual([p['musicians'] for p in itapevi['points']],[4,2])
        self.assertEqual(len(cotia['points']),1)
        self.assertIsNone(cotia['summary']['change'])

    def test_different_simultaneous_circuits_never_generate_decline(self):
        e,r,l=self.fixture();e=e[:2]
        e[0]['data_evento']='2026-07-19'
        l[0]['nome']='COTIA'
        for row in r:
            if row['evento_id']=='a':row['municipio_informado']='COTIA'
        data=evolution(e,r,l,{'evento':'b'})
        self.assertFalse(data['comparable'])
        self.assertEqual(len(data['points']),1)
        self.assertIsNone(data['metrics']['musicians']['change'])
        self.assertTrue(all(s['summary']['change'] is None for s in data['municipalities']))

    def test_visiting_another_circuit_does_not_create_municipal_decline(self):
        e,r,l=self.fixture();e=e[:2];e[0]['data_evento']='2026-07-19';l[0]['nome']='COTIA'
        # Pessoas de Itapevi em Cotia são visitas, não outro ensaio de Itapevi.
        data=evolution(e,r,l,{'evento':'b'})
        city=next(x for x in data['municipalities'] if x['name']=='ITAPEVI')
        self.assertEqual(len(city['points']),1)
        self.assertIsNone(city['summary']['change'])

    def test_same_circuit_but_different_host_coverage_is_not_comparable(self):
        e,r,l=self.fixture();l.append({'id':'extra','evento_id':'a','nome':'PIRAPORA'})
        data=evolution(e,r,l,{'evento':'b'})
        self.assertFalse(data['comparable'])
        self.assertIsNone(data['metrics']['total']['change'])

    def test_all_circuits_without_selected_event_do_not_create_global_trend(self):
        e,r,l=self.fixture();e[0]['data_evento']='2026-07-19';l[0]['nome']='COTIA'
        data=evolution(e,r,l,{'tipo':'ENSAIO_REGIONAL'})
        self.assertFalse(data['comparable'])
        self.assertEqual(data['points'],[])

    def test_selected_september_event_never_offers_july_city_series(self):
        e,r,l=self.fixture();e[0]['data_evento']='2026-07-19';l[0]['nome']='JANDIRA'
        for row in r:
            if row['evento_id']=='a':row['municipio_informado']='JANDIRA'
        data=evolution(e,r,l,{'evento':'b'})
        self.assertEqual({x['name'] for x in data['municipalities']},{'ITAPEVI'})
        self.assertEqual(data['municipalities'][0]['points'][0]['date'],'2026-09-20')
