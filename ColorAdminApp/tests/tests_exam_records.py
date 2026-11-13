import json
from unittest.mock import patch, Mock
from django.test import RequestFactory, SimpleTestCase
from django.http import HttpResponse
from ColorAdminApp import music_exams


class ExamRecordPresentationTests(SimpleTestCase):
    @patch('ColorAdminApp.music_exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.music_exams.render',return_value=HttpResponse('Exames'))
    def test_exam_page_is_not_cached_after_visual_updates(self,render,access):
        request=RequestFactory().get('/musica/exames/')
        request.session={'user_profile':{'role_id':1}}
        response=music_exams.page(request)
        self.assertIn('no-store',response['Cache-Control'])

    def test_approval_label_follows_category_without_changing_stored_result(self):
        row={'resultado':'APROVADO','categoria':'ORGANISTA'}
        self.assertEqual(music_exams.result_label(row),'APROVADA')
        self.assertEqual(row['resultado'],'APROVADO')
        self.assertEqual(music_exams.result_label({'resultado':'APROVADO','instrumento':'ÓRGÃO'}),'APROVADA')
        self.assertEqual(music_exams.result_label({'resultado':'APROVADO','categoria':'MÚSICO','instrumento':'VIOLINO'}),'APROVADO')
        self.assertEqual(music_exams.result_label({'resultado':'AUSENTE','categoria':'ORGANISTA'}),'AUSENTE')

    def test_legacy_import_metadata_is_hidden_without_losing_agenda_or_human_notes(self):
        restored=music_exams.restore_agenda({'observacoes':
            'Importado de: arquivo.pdf\nData confirmada pelo solicitante: 07/11/2026.\n'
            'Nome anterior no cadastro: Ana\nNome no documento: Ana Silva\n'
            'Precisa apresentar a prova original.\nAgenda: Avaliação de Organistas | 07/11/2026 09:00 | ID: abc123'})
        self.assertEqual(restored['observacoes'],'Precisa apresentar a prova original.')
        self.assertEqual(restored['agenda_evento_id'],'abc123')
        self.assertEqual(restored['agenda_evento_data'],'2026-11-07')
        self.assertEqual(music_exams.restore_agenda(restored),restored)

    @patch('ColorAdminApp.music_exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.music_exams.requests.get')
    def test_student_search_is_bounded_and_scope_checked(self,get,access):
        request=RequestFactory().get('/musica/exames/api/alunos/',{'q':'Ana'})
        request.session={'user_profile':{'access_level':'local','comum':'BR-22-1234 - CENTRAL','municipio':'ITAPEVI'}}
        get.return_value.json.return_value=[
            {'id':'local','nome_aluno':'Ana Silva','comum_congregacao':'BR-22-1234 - CENTRAL','municipio':'ITAPEVI'},
            {'id':'outside','nome_aluno':'Ana Santos','comum_congregacao':'BR-22-9999 - OUTRA','municipio':'ITAPEVI'}]
        response=music_exams.api_student_search(request)
        self.assertEqual([r['id'] for r in json.loads(response.content)['items']],['local'])
        params=get.call_args.kwargs['params']
        self.assertEqual(params['limit'],30)
        self.assertEqual(params['comum_congregacao'],'eq.BR-22-1234 - CENTRAL')
        self.assertEqual(params['nome_aluno'],'ilike.*Ana*')

    @patch('ColorAdminApp.music_exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.music_exams.requests.get')
    def test_empty_or_one_letter_search_does_not_read_roster(self,get,access):
        request=RequestFactory().get('/musica/exames/api/alunos/',{'q':'A'})
        request.session={'user_profile':{'role_id':1}}
        self.assertEqual(json.loads(music_exams.api_student_search(request).content)['items'],[])
        get.assert_not_called()

    @patch('ColorAdminApp.music_exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.music_exams.fetch_rows',return_value=[])
    @patch('ColorAdminApp.music_exams.fetch_legacy',return_value=[])
    @patch('ColorAdminApp.music_exams.visible_students')
    def test_dashboard_never_fetches_the_entire_roster(self,students,legacy,rows,access):
        request=RequestFactory().get('/musica/exames/api/dashboard/')
        request.session={'user_profile':{'role_id':1}}
        response=music_exams.api_dashboard(request)
        self.assertEqual(response.status_code,200)
        self.assertEqual(json.loads(response.content)['students'],[])
        students.assert_not_called()
