from unittest.mock import Mock,patch
from django.test import RequestFactory,SimpleTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from ColorAdminApp import exam_documents


class ExamDocumentTests(SimpleTestCase):
    def request(self,file=None):
        request=RequestFactory().post('/musica/exames/api/registros/exam/anexo/',{'prova':file} if file else {})
        request.session={'user_profile':{'role_id':1}}
        return request

    @patch('ColorAdminApp.exam_documents.exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.exam_documents.requests.patch')
    @patch('ColorAdminApp.exam_documents.requests.post')
    @patch('ColorAdminApp.exam_documents.requests.get')
    def test_attachment_changes_only_document_fields(self,get,upload,update,access):
        row=dict(id='exam',aluno_id='student',municipio='ITAPEVI',comum='CENTRAL',tipo_exame='RJM',resultado='APROVADO',observacoes='Nota manual')
        get.return_value.json.return_value=[row]
        update.return_value.json.return_value=[dict(row,prova_nome='carta.pdf',prova_url='student/proof.pdf')]
        result=exam_documents.api_attachment(self.request(SimpleUploadedFile('carta.pdf',b'%PDF-1.7\nDocument',content_type='application/pdf')),'exam')
        self.assertEqual(result.status_code,200,result.content)
        self.assertEqual(set(update.call_args.kwargs['json']),{'prova_url','prova_nome'})
        self.assertEqual(update.call_args.kwargs['params'],{'id':'eq.exam','municipio':'eq.ITAPEVI','comum':'eq.CENTRAL'})
        self.assertEqual(upload.call_args.kwargs['headers']['Content-Type'],'application/pdf')
        self.assertEqual(upload.call_count,1)

    @patch('ColorAdminApp.exam_documents.exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.exam_documents.requests.get')
    @patch('ColorAdminApp.exam_documents.requests.post')
    def test_another_common_is_not_allowed_to_attach(self,upload,get,access):
        request=self.request(SimpleUploadedFile('carta.pdf',b'%PDF-1.7',content_type='application/pdf'))
        request.session={'user_profile':{'access_level':'local','comum':'MY COMMON','municipio':'ITAPEVI'}}
        get.return_value.json.return_value=[dict(id='exam',aluno_id='student',municipio='ITAPEVI',comum='OTHER COMMON')]
        self.assertEqual(exam_documents.api_attachment(request,'exam').status_code,404)
        upload.assert_not_called()

    @patch('ColorAdminApp.exam_documents.exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.exam_documents.requests.get')
    @patch('ColorAdminApp.exam_documents.requests.post')
    def test_invalid_extension_or_content_never_uploads(self,upload,get,access):
        get.return_value.json.return_value=[dict(id='exam',aluno_id='student',municipio='ITAPEVI',comum='CENTRAL')]
        self.assertEqual(exam_documents.api_attachment(self.request(SimpleUploadedFile('file.svg',b'<svg/>')),'exam').status_code,400)
        self.assertEqual(exam_documents.api_attachment(self.request(SimpleUploadedFile('file.pdf',b'not a PDF')),'exam').status_code,400)
        self.assertEqual(exam_documents.api_attachment(self.request(),'exam').status_code,400)
        upload.assert_not_called()

    @patch('ColorAdminApp.exam_documents.exams.can_open_module',return_value=False)
    @patch('ColorAdminApp.exam_documents.requests.get')
    def test_module_access_is_required(self,get,access):
        self.assertEqual(exam_documents.api_attachment(self.request(),'exam').status_code,403)
        get.assert_not_called()
