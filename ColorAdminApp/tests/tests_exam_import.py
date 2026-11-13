import io
import json
from unittest.mock import patch, Mock
from django.test import SimpleTestCase, RequestFactory
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook
from ColorAdminApp.exam_import import table_rows, text_rows, read_document, result_kind
from ColorAdminApp.exam_import_api import row_payload, resolve_student, import_exams
from ColorAdminApp import music_exams


class ExamImportTests(SimpleTestCase):
    def setUp(self):
        self.student = dict(id='student', nome_aluno='Ana Silva', comum_congregacao='BR-22-1234 - CENTRAL',
                            municipio='PIRAPORA DO BOM JESUS', instrumento='ÓRGÃO', cargo_ministerio='ORGANISTA', nivel='CANDIDATO(A)')
        self.row = dict(nome='Ana Silva', comum='BR-22-1234 - CENTRAL', tipo_exame='RJM', resultado='APROVADO')
        self.event = dict(id='evt', titulo='Exame de Organistas (Santana de Parnaíba)', data='2026-10-24', hora='09:00', url='https://ccbagenda.vercel.app/')
        self.request = RequestFactory().post('/')
        self.request.session = {'user_profile': {'full_name':'Secretaria'}}

    def test_headers_and_empty_results_do_not_invent_approvals(self):
        rows=table_rows([['NOME','COMUM','INSTRUTORA'],['Ana Silva','BR-22-1234 - CENTRAL','Maria']], 'RJM')
        self.assertEqual(rows[0]['resultado'], 'AGENDADO')
        self.assertEqual(result_kind('REPROVADA'), 'RETORNOU AO CICLO')

    def test_pdf_layout_tracks_sections(self):
        rows=text_rows('PARA EXAME DE OFICIALIZAÇÃO\n1 ANA SILVA    BR-22-1234 - CENTRAL    MARIA    APROVADA\nPARA TESTE RJM\n2 BIA SILVA    BR-22-1234 - CENTRAL    MARIA    AUSENTE')
        self.assertEqual([r['tipo_exame'] for r in rows], ['OFICIALIZAÇÃO','RJM'])
        self.assertEqual(rows[0]['nome'],'ANA SILVA')
        self.assertEqual(rows[1]['resultado'],'AUSENTE')

    def test_common_and_homonyms_require_unambiguous_match(self):
        self.assertEqual(resolve_student(self.row,[self.student]),self.student)
        self.assertIsNone(resolve_student(self.row,[self.student,dict(self.student,id='other')]))
        self.assertIsNone(resolve_student(dict(self.row,comum='BR-22-9999'),[self.student]))

    def test_particles_married_surname_and_spelling_match_within_common(self):
        for source, stored in [('ISADORA CUBAS CARREIRO CALONGAS','ISADORA CUBAS CARREIRO'),
                               ('ELAINE DE OLIVEIRA SILVA','ELAINE DE OLIVEIRA DA SILVA'),
                               ('DENISE MARIA DA SILVA','DENISE MARIA SILVA'),
                               ('MARIANA CIRYNEO ANDRE SILVEIRA','MARIANA CYRINEO ANDRÉ SILVEIRA'),
                               ('ISABELLA FERNANDES DE SOUSA','ISABELLA FERNANDES DE CASTRO')]:
            student=dict(self.student,nome_aluno=stored)
            self.assertEqual(resolve_student(dict(self.row,nome=source),[student]),student)

    def test_surname_similarity_never_matches_another_given_name(self):
        for source, stored in [('RAQUEL MATIAS CORREIA','MIGUEL MATIAS CORREIA'),
                               ('HELEN VITÓRIA DOMINGUES DA SILVA','RICARDO DOMINGUES DA SILVA')]:
            self.assertIsNone(resolve_student(dict(self.row,nome=source),[dict(self.student,nome_aluno=stored)]))

    def test_new_student_requires_catalog_scope_and_does_not_invent_consent(self):
        from ColorAdminApp.exam_identity import new_student_plan
        request=self.request;request.session['user_profile']['access_level']='municipal'
        request.session['user_profile']['municipio']='PIRAPORA DO BOM JESUS'
        catalog=[{'comum':'BR-22-1234 - CENTRAL','cidade':'PIRAPORA DO BOM JESUS'}]
        row=dict(self.row,categoria='ORGANISTA')
        student=new_student_plan(row,{},request,catalog)
        self.assertEqual(student['instrumento'],'ÓRGÃO')
        self.assertFalse(student['consentimento_lgpd'])
        self.assertNotIn('data_nascimento',student)
        self.assertEqual(student['id'],new_student_plan(row,{},request,catalog)['id'])
        with self.assertRaises(ValueError):
            new_student_plan(row,{},request,[dict(catalog[0],cidade='ITAPEVI')])

    @patch('ColorAdminApp.music_exams.requests.get')
    def test_import_student_query_is_limited_to_document_commons(self,get):
        request=self.request;request.session['user_profile']['role_id']=1
        get.return_value.json.return_value=[self.student]
        self.assertEqual(music_exams.visible_students(request,{'BR-22-1234'}),[self.student])
        params=get.call_args.kwargs['params']
        self.assertEqual(params['or'],'(comum_congregacao.ilike.BR-22-1234*)')
        self.assertEqual(params['limit'],1000)

    @patch('ColorAdminApp.exam_identity.requests.patch')
    def test_rename_keeps_student_id_and_does_not_replace_other_fields(self,update):
        from ColorAdminApp.exam_identity import save_identity
        old=dict(self.student,nome_aluno='ISADORA CUBAS CARREIRO')
        updated=dict(old,nome_aluno='ISADORA CUBAS CARREIRO CALONGAS')
        cache.set('gem:students:v7',[old],300)
        update.return_value.json.return_value=[updated]
        result=save_identity(old,dict(self.row,nome=updated['nome_aluno']),{'atualizar_nome':True})
        self.assertEqual(result['id'],old['id'])
        self.assertEqual(update.call_args.kwargs['json'],{'nome_aluno':updated['nome_aluno']})
        self.assertEqual(cache.get('gem:students:v7')[0]['nome_aluno'],updated['nome_aluno'])

    @patch('ColorAdminApp.exam_import_api.common_catalog')
    @patch('ColorAdminApp.exam_import_api.save_identity')
    @patch('ColorAdminApp.music_exams.update_student_stage')
    @patch('ColorAdminApp.music_exams.sync_shared_exam')
    @patch('ColorAdminApp.music_exams.save_exam')
    @patch('ColorAdminApp.music_exams.fetch_rows',return_value=[])
    @patch('ColorAdminApp.music_exams.agenda_events')
    @patch('ColorAdminApp.music_exams.visible_students',return_value=[])
    @patch('ColorAdminApp.music_exams.can_open_module',return_value=True)
    def test_missing_student_is_created_only_after_whole_batch_validation(self,access,students,agenda,fetch,save,shared,stage,identity,catalog):
        from ColorAdminApp.exam_import_api import owner
        self.request.session['user_profile']['role_id']=1
        catalog.return_value=[{'comum':self.student['comum_congregacao'],'cidade':self.student['municipio']}]
        agenda.return_value=[self.event]
        identity.side_effect=lambda student,*args: student
        save.side_effect=lambda payload:dict(payload,id='exam')
        cache.set('exam-import:new-test',{'owner':owner(self.request),'rows':[dict(self.row,categoria='ORGANISTA')]},60)
        choice=dict(linha=0,criar_cadastro=True,categoria='ORGANISTA',data_exame='invalid')
        def submit(validate=False):
            request=RequestFactory().post('/',json.dumps({'token':'new-test','items':[choice],'validar_apenas':validate}),content_type='application/json')
            request.session=self.request.session
            return import_exams(request)
        self.assertEqual(submit().status_code,400)
        identity.assert_not_called();save.assert_not_called()
        choice['data_exame']='2026-10-24'
        self.assertEqual(submit(True).status_code,200)
        identity.assert_not_called();save.assert_not_called()
        response=submit()
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(json.loads(response.content)['cadastrados'],1)
        self.assertFalse(identity.call_args.args[0]['consentimento_lgpd'])
        self.assertEqual(save.call_args.args[0]['tipo_exame'],'RJM')

    def test_preview_selector_does_not_repeat_the_regional_roster(self):
        from pathlib import Path
        text=(Path(__file__).resolve().parents[1]/'templates/pages/music_exams.html').read_text(encoding='utf-8')
        render=text.split('function importRender(d)',1)[1].split("$('#import-apply')",1)[0]
        self.assertNotIn('state.students.map',render)
        self.assertIn('r.candidates',render)
        self.assertIn('AbortSignal.timeout(90000)',text)

    def test_date_resolves_group_and_category_and_manual_history(self):
        choice=dict(aluno_id='student', data_exame='2026-10-24')
        student,payload=row_payload(self.row,choice,{'student':self.student},[self.event],self.request)
        self.assertEqual(payload['agenda_evento_id'],'evt')
        self.assertEqual(music_exams.dashboard_summary([],[payload])[1]['organistas_rjm'],1)
        self.assertEqual(music_exams.regional_group(payload['municipio']),'SANTANA / PIRAPORA')
        with self.assertRaises(ValueError):
            row_payload(self.row,choice,{'student':self.student},[],self.request)
        choice['historico_sem_agenda']=True
        self.assertNotIn('agenda_evento_id',row_payload(self.row,choice,{'student':self.student},[],self.request)[1])

    def test_cross_scope_and_wrong_common_are_rejected(self):
        with self.assertRaises(ValueError):
            row_payload(self.row,{'aluno_id':'outside'}, {}, [], self.request)
        with self.assertRaises(ValueError):
            row_payload(dict(self.row,comum='BR-22-9999'),{'aluno_id':'student'}, {'student':self.student}, [], self.request)

    def test_workbook_skips_general_duplicates(self):
        w=Workbook();w.active.title='RJM';w.active.append(['NOME','COMUM']);w.active.append(['Ana','BR-22-1234'])
        general=w.create_sheet('GERAL');general.append(['NOME','COMUM']);general.append(['Ana','BR-22-1234'])
        data=io.BytesIO();w.save(data)
        self.assertEqual(len(read_document(SimpleUploadedFile('lista.xlsx',data.getvalue()))),1)

    @patch('ColorAdminApp.music_exams.can_open_module', return_value=True)
    @patch('ColorAdminApp.music_exams.visible_students')
    @patch('ColorAdminApp.music_exams.agenda_events')
    @patch('ColorAdminApp.music_exams.fetch_rows', return_value=[])
    @patch('ColorAdminApp.music_exams.save_exam')
    def test_preview_does_not_write_and_commit_revalidates(self,save,fetch,agenda,students,access):
        students.return_value=[self.student];agenda.return_value=[self.event]
        req=RequestFactory().post('/',{'arquivo':SimpleUploadedFile('lista.csv',b'NOME;COMUM;TIPO;RESULTADO\nAna Silva;BR-22-1234;RJM;APROVADA')})
        req.session=self.request.session
        result=import_exams(req);body=json.loads(result.content)
        self.assertEqual(result.status_code,200);save.assert_not_called()
        students.return_value=[]
        req=RequestFactory().post('/',json.dumps({'token':body['token'],'items':[dict(linha=0,aluno_id='student',data_exame='2026-10-24')]}),content_type='application/json')
        req.session=self.request.session
        self.assertEqual(import_exams(req).status_code,400);save.assert_not_called()

    @patch('ColorAdminApp.music_exams.can_open_module', return_value=True)
    @patch('ColorAdminApp.music_exams.fetch_rows')
    @patch('ColorAdminApp.music_exams.fetch_legacy', return_value=[])
    def test_history_exports_respect_filters_and_identity(self,legacy,rows,access):
        rows.return_value=[dict(id='exam',nome_aluno='Ana Silva',municipio='Pirapora',comum='Central',data_exame='2026-10-24',tipo_exame='RJM',resultado='APROVADO',origem='IMPORTACAO',categoria='ORGANISTA')]
        req=RequestFactory().get('/?historico=1&q=Ana');req.session=self.request.session
        result=music_exams.export_excel(req)
        w=load_workbook(io.BytesIO(result.content),rich_text=True)
        self.assertEqual(w.sheetnames,['Registros Individuais'])
        self.assertIn('Secretaria Regional da Música',str(w.active['A4'].value))
        self.assertEqual(w.active['H7'].value,'24/10/2026')
        self.assertEqual(w.active['I7'].value,'APROVADA')
        pdf=music_exams.export_pdf(req)
        from pypdf import PdfReader
        text=PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
        self.assertIn('Ana Silva',text);self.assertIn('24/10/2026',text)
        self.assertIn('APROVADA',text)
        self.assertIn('Secretaria Regional da Música',text)

    @patch('ColorAdminApp.music_exams.update_student_stage')
    @patch('ColorAdminApp.music_exams.sync_shared_exam')
    @patch('ColorAdminApp.music_exams.save_exam')
    @patch('ColorAdminApp.music_exams.fetch_rows', return_value=[])
    @patch('ColorAdminApp.music_exams.agenda_events')
    @patch('ColorAdminApp.music_exams.visible_students')
    @patch('ColorAdminApp.music_exams.can_open_module', return_value=True)
    def test_commit_synchronizes_and_token_is_bound_to_session(self,access,students,agenda,rows,save,shared,stage):
        from ColorAdminApp.exam_import_api import owner
        students.return_value=[self.student];agenda.return_value=[self.event]
        save.side_effect=lambda payload:dict(payload,id='exam')
        cache.set('exam-import:test-token',{'owner':owner(self.request),'rows':[self.row]},60)
        payload={'token':'test-token','items':[dict(linha=0,aluno_id='student',data_exame='2026-10-24')]}
        req=RequestFactory().post('/',json.dumps(payload),content_type='application/json');req.session={}
        self.assertEqual(import_exams(req).status_code,400);save.assert_not_called()
        req.session=self.request.session
        result=import_exams(req)
        self.assertEqual(result.status_code,200,result.content)
        shared.assert_called_once();stage.assert_called_once()
        self.assertEqual(save.call_args.args[0]['data_exame'],'2026-10-24')

    @patch('ColorAdminApp.gem.can_open_module', return_value=True)
    @patch('ColorAdminApp.gem.can_access', return_value=True)
    @patch('ColorAdminApp.gem.requests.get')
    @patch('ColorAdminApp.gem.requests.patch')
    @patch('ColorAdminApp.music_exams.save_exam')
    @patch('ColorAdminApp.music_exams.sync_shared_exam')
    @patch('ColorAdminApp.music_exams.update_student_stage')
    def test_student_registration_preserves_individual_historical_dates(self,stage,shared,save,update,get,scope,access):
        from ColorAdminApp.gem import api_student_detail
        def respond(url, **kwargs):
            response=Mock();response.json.return_value=[self.student] if url.endswith('musica_acompanhamento_aluno') else []
            return response
        get.side_effect=respond;update.return_value.json.return_value=[self.student]
        save.side_effect=lambda payload:dict(payload,id='exam')
        req=RequestFactory().patch('/',json.dumps({'nome_aluno':'Ana Silva','data_exame_rjm':'2024-03-10',
                                                  'data_exame_culto':'2025-05-11','data_exame_oficializacao':'2026-10-24'}),content_type='application/json')
        req.session=self.request.session
        result=api_student_detail(req,'student')
        self.assertEqual(result.status_code,200,result.content)
        self.assertEqual([call.args[0]['data_exame'] for call in save.call_args_list],['2024-03-10','2025-05-11','2026-10-24'])
        self.assertEqual(shared.call_count,3)
