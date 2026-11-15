import io
import json
from datetime import datetime
from unittest.mock import Mock,patch
from django.test import SimpleTestCase,RequestFactory,override_settings
from openpyxl import load_workbook
from pypdf import PdfReader
from ColorAdminApp.modules.music_events_conductors import summarize
from ColorAdminApp.modules.music_events_dashboard import aggregate
from ColorAdminApp.modules.music_events_reports import build_excel,build_pdf
from ColorAdminApp.modules import music_events


class ConductorSummaryTests(SimpleTestCase):
    def test_sick_and_without_conductor_are_preserved_in_reports(self):
        from ColorAdminApp.modules.music_events_conductors import attendance_status, attendance_label
        from ColorAdminApp.modules.music_events_annual_reports import leader_text
        for state, label, short in [('ENFERMO', 'ENFERMO', 'EF'), ('SEM_ENCARREGADO', 'SEM ENCARREGADO', 'SE')]:
            row = {'situacao': state}
            self.assertEqual(attendance_status(row), state)
            self.assertEqual(attendance_label(row), label)
            self.assertEqual(leader_text(row), short)

    def test_legacy_not_informed_is_counted_as_nj(self):
        from ColorAdminApp.modules.music_events_conductors import attendance_status
        events, _, sites = self.fixture()
        catalog = [{'comum': 'BR-22-1 - A', 'cidade': 'COTIA'},
                   {'comum': 'BR-22-2 - B', 'cidade': 'COTIA'}]
        reviews = [
            {'evento_id': 'e', 'comum_chave': 'BR-22-1', 'comum_nome': catalog[0]['comum'],
             'municipio': 'COTIA', 'situacao': 'NAO_INFORMADO'},
            {'evento_id': 'e', 'comum_chave': 'BR-22-2', 'comum_nome': catalog[1]['comum'],
             'municipio': 'COTIA', 'situacao': 'NAO_JUSTIFICOU'},
        ]
        data = summarize(events, [], sites, reviews, {}, catalog=catalog)

        self.assertEqual(attendance_status({'situacao': 'NAO_INFORMADO'}), 'NAO_JUSTIFICOU')
        self.assertEqual(data['totals'].get('NAO_INFORMADO',0), 0)
        self.assertEqual(data['totals']['NAO_JUSTIFICOU'], 2)

    def fixture(self):
        events=[{'id':'e','titulo':'Ensaio Regional','data_evento':'2026-07-19','tipo':'ENSAIO_REGIONAL','familia':'GERAL','status':'ABERTO'}]
        sites=[{'id':'l','evento_id':'e','nome':'CAUCAIA DO ALTO'}]
        records=[{'evento_id':'e','local_id':'l','nome':'Encarregado de teste','comum_informada':'BR-22-1 - A','municipio_informado':'COTIA','cargo':'ENCARREGADO LOCAL','categoria':'MUSICO'},
                 {'evento_id':'e','local_id':'l','comum_informada':'BR-22-2 - B','municipio_informado':'COTIA','categoria':'MUSICO'}]
        return events,records,sites

    def test_nominal_present_and_default_nj_are_distinct(self):
        e,r,l=self.fixture();data=summarize(e,r,l,[],{})
        self.assertEqual(data['rows'][0]['registro'],'PRESENTE')
        self.assertEqual(data['rows'][0]['locais_validos'],['CAUCAIA DO ALTO'])
        self.assertEqual(data['rows'][1]['situacao'],'NAO_JUSTIFICOU')
        self.assertEqual(data['totals'].get('NAO_JUSTIFICOU',0),1)

    def test_registered_leader_in_nominal_list_is_present_even_without_imported_role(self):
        e,r,l=self.fixture();r[0]['cargo']='MÚSICO'
        leaders=[{'nome_aluno':'Encarregado de teste','cargo_ministerio':'ENCARREGADO LOCAL',
                  'comum_congregacao':'BR-22-1 - A','municipio':'COTIA','status':'Ativo'}]
        data=summarize(e,r,l,[],{},catalog=[{'comum':'BR-22-1 - A','cidade':'COTIA'}],leaders=leaders)
        row=next(x for x in data['rows'] if x['comum_chave']=='BR-22-1')
        self.assertEqual(row['situacao'],'PRESENTE')
        self.assertEqual(row['registro'],'PRESENTE')

    def test_registered_name_resolves_unrecognized_itapevi_common(self):
        e,r,l=self.fixture();r[0].update(cargo='MÚSICO',comum_informada='ITACOLMY',municipio_informado='ITAPEVI',nome='Claudio')
        catalog=[{'comum':'BR-22-3270 - JARDIM ITACOLOMI','cidade':'ITAPEVI'}]
        leaders=[{'nome_aluno':'Claudio','cargo_ministerio':'ENCARREGADO LOCAL',
                  'comum_congregacao':'BR-22-3270 - JARDIM ITACOLOMI','municipio':'ITAPEVI','status':'Ativo'}]
        data=summarize(e,r,l,[],{},catalog=catalog,leaders=leaders)
        row=next(x for x in data['rows'] if x['comum_chave']=='BR-22-3270')
        self.assertEqual(row['situacao'],'PRESENTE')

    def test_manual_status_does_not_erase_nominal_presence(self):
        e,r,l=self.fixture()
        review={'evento_id':'e','comum_chave':'BR-22-1','comum_nome':'A','municipio':'COTIA',
                'situacao':'NAO_INFORMADO','observacoes':'','local_id':None}
        data=summarize(e,r,l,[review],{})
        self.assertEqual(data['rows'][0]['situacao'],'PRESENTE')

    def test_nominal_presence_is_not_overridden_by_a_saved_justification(self):
        e,r,l=self.fixture()
        r.append(dict(r[0],comum_informada='BR-22-3 - C',nome='Outro encarregado'))
        review={'evento_id':'e','comum_chave':'BR-22-1','comum_nome':'A','municipio':'COTIA',
                'situacao':'JUSTIFICOU','observacoes':'Viagem','local_id':None}
        data=summarize(e,r,l,[review],{})
        row=next(item for item in data['rows'] if item['comum_chave']=='BR-22-1')
        self.assertEqual(row['situacao'],'PRESENTE')
        self.assertEqual(data['totals'].get('JUSTIFICOU',0),0)
        self.assertEqual(data['totals'].get('PRESENTE',0),2)

    def test_musician_before_conductor_does_not_leave_an_empty_conference(self):
        e,r,l=self.fixture()
        musician=dict(r[0],nome='Músico anterior',cargo='MÚSICO')
        for records in ([musician,r[0]],[r[0],musician]):
            data=summarize(e,records,l,[],{})
            self.assertEqual(len(data['rows']),1)
            self.assertEqual(data['rows'][0]['encarregado_nome'],'Encarregado de teste')
            self.assertEqual(data['rows'][0]['registro'],'PRESENTE')
            self.assertEqual(data['totals'].get('NAO_INFORMADO',0),0)

    def test_common_representation_is_present_with_another_pending_conductor(self):
        from ColorAdminApp.modules.music_events_conductors import attach_common_attendance, attendance_status
        e,r,l=self.fixture()
        review={'evento_id':'e','comum_chave':'BR-22-1','comum_nome':'A','municipio':'COTIA',
                'encarregado_nome':'Outro encarregado','situacao':'NAO_INFORMADO'}
        data=aggregate(e,r[:1],l,[],{})
        data['conductors']=summarize(e,r[:1],l,[review],{})
        self.assertEqual(len(data['conductors']['rows']),2)
        attach_common_attendance(data)
        self.assertEqual(attendance_status(data['rows'][0]),'PRESENTE')
        self.assertTrue(data['rows'][0]['encarregado_na_lista'])
        data['report']='comuns'
        pdf=PdfReader(io.BytesIO(build_pdf(data,'Validação',datetime(2026,11,15,12))))
        self.assertIn('PRESENTE',pdf.pages[0].extract_text())
        self.assertNotIn('NÃO INFORMADO',pdf.pages[0].extract_text().split('LEGENDA')[0])
        book=load_workbook(io.BytesIO(build_excel(data,'Validação',datetime(2026,11,15,12))))
        self.assertEqual(book.active['C10'].value,'PRESENTE')

    def test_explicit_nominal_flag_is_preserved_by_report_status(self):
        from ColorAdminApp.modules.music_events_conductors import attendance_status
        from ColorAdminApp.modules.music_events_annual_reports import leader_text
        for flag in ['consta_lista','encarregado_na_lista','leader_on_list']:
            row={flag:True,'leader_attendance':'NAO_INFORMADO','situacao':'NAO_INFORMADO'}
            self.assertEqual(attendance_status(row),'PRESENTE')
            self.assertEqual(leader_text(row),'PRESENTE')

    def test_same_common_tracks_each_conductor_state_independently(self):
        events, records, sites = self.fixture()
        catalog=[{'comum':'BR-22-1 - A','cidade':'COTIA'}]
        leaders=[
            {'nome_aluno':'Encarregado mais antigo','cargo_ministerio':'ENCARREGADO LOCAL',
             'comum_congregacao':catalog[0]['comum'],'municipio':'COTIA','status':'Ativo'},
            {'nome_aluno':'Encarregado auxiliar','cargo_ministerio':'ENCARREGADO LOCAL AUXILIAR',
             'comum_congregacao':catalog[0]['comum'],'municipio':'COTIA','status':'Ativo'},
        ]
        records[0].update(nome='Encarregado auxiliar',cargo='MÚSICO')
        review={'evento_id':'e','comum_chave':'BR-22-1','comum_nome':catalog[0]['comum'],
                'municipio':'COTIA','encarregado_nome':'Encarregado mais antigo',
                'situacao':'JUSTIFICOU','observacoes':'Viagem','local_id':None}
        data=summarize(events,records,sites,[review],{},catalog=catalog,leaders=leaders)
        same_common=[row for row in data['rows'] if row['comum_chave']=='BR-22-1']
        self.assertEqual({row['encarregado_nome']:row['situacao'] for row in same_common},
                         {'Encarregado mais antigo':'JUSTIFICOU','Encarregado auxiliar':'PRESENTE'})

    def test_manual_justification_can_include_common_with_no_attendance(self):
        e,r,l=self.fixture();review={'evento_id':'e','comum_chave':'BR-22-3','comum_nome':'Comum C','municipio':'COTIA','situacao':'JUSTIFICOU','observacoes':'Trabalho','local_id':None}
        data=summarize(e,r,l,[review],{})
        self.assertEqual(data['totals']['JUSTIFICOU'],1)
        self.assertEqual(data['municipalities'][0]['JUSTIFICOU'],1)
        self.assertEqual(next(x for x in data['rows'] if x['comum_chave']=='BR-22-3')['registro'],'JUSTIFICOU')

    def test_reports_reference_site_and_presence_at_another_rehearsal(self):
        e,r,l=self.fixture();l.append({'id':'other','evento_id':'e','nome':'JANDIRA'});r[0]['local_id']='other'
        frequency=[{'evento_id':'e','comum_codigo':'BR-22-1','local_referencia_id':'l'}]
        data=summarize(e,r,l,[],{},frequency=frequency)
        row=next(x for x in data['rows'] if x['comum_chave']=='BR-22-1')
        self.assertEqual(row['local_referencia'],'CAUCAIA DO ALTO')
        self.assertTrue(row['em_outro_local'])
        self.assertTrue(row['fora_municipio'])
        self.assertEqual(row['participacao'],'FORA DO MUNICÍPIO')
        self.assertEqual(row['registro'],'PRESENTE')
        self.assertEqual(row['locais_validos'],['JANDIRA'])
        self.assertEqual(data['municipalities'][0]['PRESENTE_OUTRO'],1)

    def test_every_convoked_common_appears_even_without_attendance(self):
        e,r,l=self.fixture()
        frequency=[{'evento_id':'e','comum_codigo':'BR-22-3','comum':'Comum C','municipio':'COTIA','local_referencia_id':'l'}]
        data=summarize(e,[],l,[],{},frequency=frequency)
        self.assertEqual(len(data['rows']),1)
        self.assertEqual(data['rows'][0]['situacao'],'NAO_JUSTIFICOU')
        self.assertEqual(data['rows'][0]['local_referencia'],'CAUCAIA DO ALTO')

    def test_period_counts_common_per_event_not_unique_people(self):
        e,r,l=self.fixture();e.append(dict(e[0],id='second'));r.append(dict(r[0],evento_id='second'))
        d=summarize(e,r,l,[],{})
        self.assertEqual(d['totals']['PRESENTE'],2)

    def test_conductor_report_includes_status_totals_and_site(self):
        e,r,l=self.fixture()
        reviews=[
            {'evento_id':'e','comum_chave':'BR-22-2','comum_nome':'B','municipio':'COTIA','situacao':'JUSTIFICOU','observacoes':'Trabalho','local_id':None},
            {'evento_id':'e','comum_chave':'BR-22-3','comum_nome':'C','municipio':'COTIA','situacao':'NAO_INFORMADO','observacoes':'','local_id':None},
        ]
        data=aggregate(e,r,l,[],{});data['conductors']=summarize(e,r,l,reviews,{});data['report']='encarregados'
        book=load_workbook(io.BytesIO(build_excel(data,'Operador',datetime(2026,10,19,12,0))))
        self.assertIn('Encarregados por município',book.sheetnames)
        ws=book['Encarregados por comum'];statuses={ws.cell(row,4).value:ws.cell(row,5).value for row in range(10,ws.max_row+1)}
        self.assertEqual(statuses['PRESENTE'],'FORA DO MUNICÍPIO')
        self.assertIn('JUSTIFICOU',statuses)
        city=book['Encarregados por município']
        self.assertEqual(city['B10'].value,1)
        self.assertEqual(city['C10'].value,1)
        self.assertEqual(city['D10'].value,1)
        self.assertEqual(city['E10'].value,0)
        text=''.join(p.extract_text() for p in PdfReader(io.BytesIO(build_pdf(data,'Operador',datetime(2026,10,19,12,0)))).pages)
        self.assertNotIn('Trabalho',text);self.assertIn('CAUCAIA DO ALTO',text);self.assertIn('PRESENTE',text);self.assertIn('JUSTIFICOU',text);self.assertNotIn('NÃO INFORMADO',text);self.assertIn('NJ',text)

    def test_manual_presence_does_not_imply_a_nominal_list_entry(self):
        e,r,l=self.fixture()
        review={'evento_id':'e','comum_chave':'BR-22-3','comum_nome':'Comum C','municipio':'COTIA',
                'situacao':'PRESENTE','observacoes':'','local_id':'l'}
        data=summarize(e,r,l,[review],{})
        row=next(item for item in data['rows'] if item['comum_chave']=='BR-22-3')
        self.assertFalse(row['consta_lista'])
        self.assertEqual(row['registro'],'PRESENTE')

    def test_invalid_destination_keeps_binary_nominal_presence(self):
        e,r,l=self.fixture()
        e[0]['data_evento']='2026-05-17'
        data=summarize(e,r,l,[],{})
        row=data['rows'][0]
        self.assertTrue(row['consta_lista'])
        self.assertEqual(row['registro'],'PRESENTE')
        self.assertEqual(row['locais_validos'],[])


@override_settings(SUPABASE_URL='https://db.example',SUPABASE_SERVICE_ROLE_KEY='test')
class ConductorApiTests(SimpleTestCase):
    def request(self,status='JUSTIFICOU',notes='Trabalho',person_name=''):
        r=RequestFactory().post('/musica/eventos/api/eventos/e/encarregado/',data=json.dumps({'comum_chave':'BR-22-1','encarregado_nome':person_name,'situacao':status,'observacoes':notes,'created_by_name':'Forjado'}),content_type='application/json')
        r.session={'authenticated':True,'user_id':'actor','user_profile':{'role_id':1,'full_name':'Operador'}};return r

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'_visible_events',return_value=[{'id':'e','status':'ABERTO'}])
    @patch.object(music_events,'common_catalog',return_value=[{'comum':'BR-22-1 - A','cidade':'COTIA'}])
    @patch.object(music_events,'_read',return_value=[])
    @patch.object(music_events.requests,'post')
    def test_authenticated_actor_and_justification(self,post,read,catalog,events,allowed):
        post.return_value=Mock();post.return_value.json.return_value=[{'id':'saved'}]
        request=self.request(person_name='Encarregado de teste')
        with patch.object(music_events,'_registry',return_value=[{'nome_aluno':'Encarregado de teste',
                'cargo_ministerio':'ENCARREGADO LOCAL','comum_congregacao':'BR-22-1 - A',
                'municipio':'COTIA','status':'ATIVO'}]), patch.object(music_events,'_leaders',return_value=[]):
            response=music_events.api_conductor(request,'e')
        self.assertEqual(response.status_code,200)
        self.assertEqual(post.call_args.kwargs['json']['created_by_name'],'Operador')
        self.assertEqual(post.call_args.kwargs['json']['encarregado_nome'],'Encarregado de teste')
        self.assertEqual(post.call_args.kwargs['json']['local_id'],None)

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'_visible_events',return_value=[{'id':'e','status':'ABERTO'}])
    @patch.object(music_events,'common_catalog',return_value=[{'comum':'BR-22-1 - A','cidade':'COTIA'}])
    @patch.object(music_events,'_read',return_value=[])
    @patch.object(music_events.requests,'post')
    def test_justification_requires_note(self,post,read,catalog,events,allowed):
        request=self.request(notes='',person_name='Encarregado de teste')
        with patch.object(music_events,'_registry',return_value=[{'nome_aluno':'Encarregado de teste',
                'cargo_ministerio':'ENCARREGADO LOCAL','comum_congregacao':'BR-22-1 - A',
                'municipio':'COTIA','status':'ATIVO'}]), patch.object(music_events,'_leaders',return_value=[]):
            self.assertEqual(music_events.api_conductor(request,'e').status_code,400)
        post.assert_not_called()

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'_visible_events',return_value=[{'id':'e','status':'ENCERRADO'}])
    @patch.object(music_events.requests,'post')
    def test_closed_event_is_immutable(self,post,events,allowed):
        self.assertEqual(music_events.api_conductor(self.request(),'e').status_code,409);post.assert_not_called()
