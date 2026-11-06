import io
import json
from datetime import date
from unittest.mock import patch
from django.test import RequestFactory, SimpleTestCase
from django.core import signing
from openpyxl import load_workbook
from pypdf import PdfReader
from ColorAdminApp.modules import music_letters_roster as domain, music_letters_roster_api as api
from ColorAdminApp.modules.music_letters_roster_exports import make_excel, make_pdf

EVENT={'id':'event','data':'2026-11-28','evento':'Avaliação Músicos - Itapevi'}
def candidate(**updates):
    row={'nome':'ALUNO DE TESTE','comum':'BR-22-2294 - JARDIM SANTA CECÍLIA','municipio':'ITAPEVI',
         'tipo':'musico','modalidade':'culto','event_id':'event','event_snapshot':EVENT,
         'instrumento':'TROMPETE','tonalidade':'Sib','delivery':{},'issued':True,'observacao':''}
    row.update(updates);row['key']=domain.candidate_key(row);return row

def letter():
    row=candidate();row.update(id='letter',payload={'instrumento':'TROMPETE','pessoa_id':'00000000-0000-4000-8000-000000000001'})
    return row

class RosterRulesTests(SimpleTestCase):
    def test_deadline_friday_on_or_before_one_calendar_month(self):
        for pre,expected in [('2026-11-28','2026-10-23'),('2026-03-31','2026-02-27'),('2026-01-31','2025-12-26')]:
            self.assertEqual(domain.suggested_deadline(pre).isoformat(),expected)

    def test_delivery_inclusive_deadline_and_overdue_boundary(self):
        limit={'deadline':'2026-10-23'}
        self.assertEqual(domain.delivery_state(candidate(),limit,date(2026,10,23)),'pending')
        self.assertEqual(domain.delivery_state(candidate(),limit,date(2026,10,24)),'overdue')
        self.assertEqual(domain.delivery_state(candidate(delivery={'received':True,'received_on':'2026-10-23'}),limit),'on_time')
        self.assertEqual(domain.delivery_state(candidate(delivery={'received':True,'received_on':'2026-10-24'}),limit),'late')

    def test_unknown_date_never_implies_on_time(self):
        self.assertEqual(domain.delivery_state(candidate(delivery={'received':True}),{'deadline':'2026-10-23'}),'unknown_date')
        self.assertEqual(domain.delivery_state(candidate(),{}),'no_deadline')

    def test_imported_candidate_and_issued_letter_count_once_preserve_receipt(self):
        c=candidate(delivery={'received':True,'received_on':'2026-10-20'})
        saved={'candidate_key':c['key'],'version':3,'data':c}
        rows=domain.merge_candidates([letter()],[saved],{'event':{'deadline':'2026-10-23'}},date(2026,11,6))
        self.assertEqual(len(rows),1);self.assertTrue(rows[0]['issued']);self.assertEqual(rows[0]['version'],3)
        self.assertEqual(rows[0]['delivery_status'],'on_time');self.assertEqual(domain.delivery_summary(rows)['delivered'],1)

    def test_different_event_and_modality_have_distinct_keys(self):
        self.assertNotEqual(candidate()['key'],candidate(event_id='other')['key'])
        self.assertNotEqual(candidate()['key'],candidate(modalidade='oficializacao')['key'])

    def test_plain_csv_reads_delivery_without_guessing_dates(self):
        rows=domain.import_rows('Nome;Comum;Carta entregue\nALUNO DE TESTE;BR-22-2294;Sim\n'.encode(),'lista.csv')
        self.assertEqual(rows[0]['received'],'Sim');self.assertNotIn('received_on',rows[0])

    def test_bad_common_is_rejected(self):
        with self.assertRaisesMessage(ValueError,'código da comum'):
            domain.import_rows(b'Nome,Comum\nAluno,Outra','x.csv')

class RosterApiTests(SimpleTestCase):
    def request(self,path='/',data=None):
        request=RequestFactory().post(path,json.dumps(data or {}),content_type='application/json')
        request.session={'user_id':'00000000-0000-4000-8000-000000000001','user_profile':{'role_id':1,'full_name':'Teste'}}
        return request

    @patch.object(api.letters,'can_review',return_value=False)
    @patch.object(api,'state')
    def test_receipt_requires_permission(self,state,allowed):
        self.assertEqual(api.save_delivery(self.request()).status_code,403);state.assert_not_called()

    @patch.object(api.letters,'can_review',return_value=True)
    @patch.object(api,'state',return_value={'items':[]})
    @patch.object(api,'rpc')
    def test_out_of_scope_candidate_cannot_be_changed(self,rpc,state,allowed):
        self.assertEqual(api.save_delivery(self.request(data={'key':'outside'})).status_code,404);rpc.assert_not_called()

    @patch.object(api.letters,'can_review',return_value=True)
    @patch.object(api,'state')
    @patch.object(api,'rpc')
    def test_future_receipt_is_rejected(self,rpc,state,allowed):
        row=candidate();state.return_value={'items':[row]}
        self.assertEqual(api.save_delivery(self.request(data={'key':row['key'],'received':True,'received_on':'2099-01-01','version':0})).status_code,400)
        rpc.assert_not_called()

    @patch.object(api.letters,'can_review',return_value=True)
    @patch.object(api,'rpc')
    def test_invalid_preview_token_never_commits(self,rpc,allowed):
        self.assertEqual(api.commit_import(self.request(data={'token':'tampered'})).status_code,400);rpc.assert_not_called()

    @patch.object(api.letters,'can_review',return_value=True)
    @patch.object(api,'rpc')
    def test_preview_token_is_bound_to_actor(self,rpc,allowed):
        token=signing.dumps({'actor':'someone-else','rows':[]},salt='letters-roster')
        self.assertEqual(api.commit_import(self.request(data={'token':token})).status_code,400);rpc.assert_not_called()

    @patch.object(api,'common_catalog',return_value=[{'comum':'BR-22-2294 - JARDIM SANTA CECÍLIA','cidade':'ITAPEVI'}])
    @patch.object(api,'read',return_value=[])
    @patch.object(api,'state',return_value={'items':[]})
    @patch('ColorAdminApp.modules.music_letters_program.assess_letters',side_effect=lambda rows:rows)
    def test_manual_import_stays_unlinked_and_duplicate_file_is_rejected(self,assess,state,read,catalog):
        raw=[{'nome':'ALUNO DE TESTE','comum':'BR-22-2294','source_row':2,'received':'Sim'}]
        result=api.prepare_import(self.request(),raw,EVENT,'musico','culto')
        self.assertIsNone(result[0]['pessoa_id']);self.assertTrue(result[0]['delivery']['received']);self.assertIsNone(result[0]['delivery']['received_on'])
        with self.assertRaisesMessage(ValueError,'duplicado'):
            api.prepare_import(self.request(),raw+raw,EVENT,'musico','culto')

class RosterExportTests(SimpleTestCase):
    def test_excel_header_filter_and_roundtrip_delivery(self):
        c=candidate(delivery={'received':True,'received_on':'2026-10-23'})
        content=make_excel([c],'Teste',{})
        workbook=load_workbook(io.BytesIO(content));sheet=workbook.active
        self.assertEqual(sheet['A1'].value,'CONGREGAÇÃO CRISTÃ NO BRASIL');self.assertEqual(sheet['K6'].value,'Carta entregue')
        self.assertEqual(sheet['K7'].value,'Sim');self.assertEqual(sheet['I7'].number_format,'dd/mm/yyyy');self.assertEqual(sheet.freeze_panes,'A7')
        imported=domain.import_rows(content,'relacao.xlsx');self.assertEqual(imported[0]['received'],'Sim');self.assertEqual(imported[0]['modalidade'],'culto')

    def test_pdf_sections_totals_and_last_checkbox_column(self):
        rows=[candidate(delivery={'received':True}),candidate(nome='ORGANISTA DE TESTE',tipo='organista',modalidade='rjm',instrumento='ÓRGÃO')]
        text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(make_pdf(rows,'Teste',{}))).pages)
        for expected in ['CONGREGAÇÃO CRISTÃ NO BRASIL','Músicos','Organistas','TOTAL DE CARTAS ENTREGUES: 1','TOTAL DE CARTAS FALTANTES: 1','CARTA']:
            self.assertIn(expected,text)


class RosterDeliveryAppearanceTests(SimpleTestCase):
    def test_notes_only_compact_status(self):
        from ColorAdminApp.modules.music_letters_roster_exports import notes
        row=candidate(activity_note='Situação GEM/SAM: INATIVO - Pendência regional',issued=False,delivery_status='late')
        self.assertEqual(notes(row,{}),'Status: Inativo')

    def test_pdf_and_excel_use_red_missing_black_delivered_and_correct_accents(self):
        import pymupdf
        rows=[candidate(nome='CANDIDATO ENTREGUE',delivery={'received':True}),
              candidate(nome='CANDIDATO FALTANTE',activity_status='INATIVO'),
              candidate(nome='OUTRO NIVEL',modalidade='oficializacao')]
        pdf=make_pdf(rows,'Teste',{})
        doc=pymupdf.open(stream=pdf,filetype='pdf')
        spans=[s for p in doc for b in p.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
        for name,color in [('CANDIDATO ENTREGUE',0),('CANDIDATO FALTANTE',16711680)]:
            self.assertTrue(any(name in s['text'] and s['color']==color for s in spans))
        text='\n'.join(p.get_text() for p in doc)
        self.assertIn('Prazo de entrega não definido',text)
        self.assertIn('Status: Inativo',text)
        self.assertNotIn('Pendência regional',text)
        self.assertIn('PARA EXAME DE OFICIALIZAÇÃO',text)
        self.assertIn('PARA TESTE CULTO OFICIAL',text)
        sheet=load_workbook(io.BytesIO(make_excel(rows,'Teste',{}))).active
        data={sheet.cell(n,2).value:n for n in range(7,sheet.max_row+1)}
        self.assertEqual(sheet.cell(data['CANDIDATO ENTREGUE'],2).font.color.rgb,'00000000')
        self.assertEqual(sheet.cell(data['CANDIDATO FALTANTE'],2).font.color.rgb,'00FF0000')
        self.assertEqual(sheet.cell(data['CANDIDATO FALTANTE'],8).value,'Status: Inativo')

class AutomaticDeadlineTests(SimpleTestCase):
    def events(self):
        return [EVENT, {'id':'pre','data':'2026-11-14','evento':'Pr\u00e9-avalia\u00e7\u00e3o de M\u00fasicos (Itapevi)'},
                {'id':'wrong-city','data':'2026-11-21','evento':'Pr\u00e9-avalia\u00e7\u00e3o de M\u00fasicos (Cotia)'},
                {'id':'wrong-kind','data':'2026-11-21','evento':'Pr\u00e9-avalia\u00e7\u00e3o de Organistas (Itapevi)'},
                {'id':'future','data':'2026-12-12','evento':'Pr\u00e9-avalia\u00e7\u00e3o de M\u00fasicos (Itapevi)'}]

    def test_exam_uses_corresponding_pre_evaluation_not_its_own_date(self):
        limits,choices=domain.effective_deadlines(self.events(),{})
        self.assertEqual(limits['event']['pre_event_id'],'pre')
        self.assertEqual(limits['event']['pre_date'],'2026-11-14')
        self.assertEqual(limits['event']['deadline'],'2026-10-09')
        self.assertEqual(limits['event']['source'],'automatic')
        self.assertEqual([e['id'] for e in choices['event']],['pre'])

    def test_pre_evaluation_uses_its_own_date(self):
        limits,_=domain.effective_deadlines(self.events(),{})
        self.assertEqual(limits['pre']['deadline'],'2026-10-09')

    def test_user_choice_takes_precedence(self):
        saved={'event':{'pre_date':'2026-11-14','deadline':'2026-10-16','version':3}}
        limits,_=domain.effective_deadlines(self.events(),saved)
        self.assertEqual(limits['event']['deadline'],'2026-10-16')
        self.assertEqual(limits['event']['suggested_deadline'],'2026-10-09')
        self.assertEqual(limits['event']['version'],3)

    def test_missing_pre_evaluation_does_not_guess_from_exam_date(self):
        limits,_=domain.effective_deadlines([EVENT],{})
        self.assertNotIn('event',limits)

    @patch.object(api,'common_catalog',return_value=[])
    @patch.object(api.letters,'visible')
    @patch.object(api,'read',return_value=[])
    @patch.object(api,'agenda_catalog')
    def test_all_events_state_applies_default_to_delivery_counts(self,agenda,read,visible,catalog):
        agenda.return_value=self.events();visible.return_value=[letter()]
        request=RequestFactory().get('/');request.session={'user_profile':{'role_id':1}}
        payload=api.state(request)
        self.assertEqual(payload['deadlines']['event']['deadline'],'2026-10-09')
        self.assertEqual(payload['items'][0]['delivery_status'],'overdue')

class OfficialCalendarDeadlineTests(SimpleTestCase):
    def official(self):
        return [EVENT, {'id':'pre-official','data':'2026-11-14','evento':'Pr\u00e9-Avalia\u00e7\u00e3o M\u00fasicos - (Itapevi)'},
                {'id':'organistas-cotia','data':'2026-11-21','evento':'Avalia\u00e7\u00e3o de Organistas (Cotia)'}]

    def test_legacy_snapshot_cannot_create_official_reference(self):
        stale={'id':'legacy','data':'2026-11-21','evento':'Pr\u00e9-avalia\u00e7\u00e3o de M\u00fasicos (Itapevi)'}
        limits,choices=domain.effective_deadlines([EVENT,stale],{},official_events=self.official())
        self.assertEqual([r['id'] for r in choices['event']],['pre-official'])
        self.assertEqual(limits['event']['pre_date'],'2026-11-14')
        self.assertNotIn('legacy',limits)

    def test_stale_saved_reference_is_not_used_and_version_is_preserved(self):
        saved={'event':{'pre_date':'2026-11-21','deadline':'2026-10-16','version':7}}
        limits,_=domain.effective_deadlines([EVENT],saved,official_events=self.official())
        self.assertEqual(limits['event']['deadline'],'2026-10-09')
        self.assertEqual(limits['event']['version'],7)
        self.assertTrue(limits['event']['stale_reference'])

    def test_official_agenda_unavailable_does_not_use_snapshots_or_saved_dates(self):
        saved={'event':{'pre_date':'2026-11-14','deadline':'2026-10-09','version':2}}
        limits,_=domain.effective_deadlines(self.official(),saved,official_events=[])
        self.assertEqual(limits,{})

    @patch.object(api.letters,'can_review',return_value=True)
    @patch.object(api,'state')
    @patch.object(api,'rpc')
    def test_pre_evaluation_date_cannot_be_forged(self,rpc,state,allowed):
        state.return_value={'events':[EVENT],'pre_options':{'event':[self.official()[1]]}}
        request=RequestFactory().post('/',json.dumps({'event_id':'event','pre_event_id':'pre-official','pre_date':'2026-11-21','deadline':'2026-10-09'}),content_type='application/json')
        request.session={'user_profile':{'role_id':1}}
        self.assertEqual(api.save_deadline(request).status_code,400)
        rpc.assert_not_called()

class ReceiptReversalTests(SimpleTestCase):
    @patch.object(api.letters,'can_review',return_value=True)
    @patch.object(api,'state')
    @patch.object(api,'rpc')
    def test_unmark_clears_receipt_date_and_preserves_version_for_audited_update(self,rpc,state,allowed):
        row=candidate(delivery={'received':True,'received_on':'2026-10-20'},version=4)
        state.return_value={'items':[row]}
        request=RequestFactory().post('/',json.dumps({'key':row['key'],'version':4,'received':False,'received_on':None}),content_type='application/json')
        request.session={'user_id':'00000000-0000-4000-8000-000000000001','user_profile':{'role_id':1,'full_name':'Teste'}}
        api.save_delivery(request)
        name,payload=rpc.call_args.args
        self.assertEqual(name,'cartas_registrar_entrega')
        self.assertFalse(payload['p_data']['delivery']['received'])
        self.assertIsNone(payload['p_data']['delivery']['received_on'])
        self.assertEqual(payload['p_version'],4)
        self.assertEqual(payload['p_data']['delivery']['recorded_by'],'Teste')
