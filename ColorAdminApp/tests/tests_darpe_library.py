import io
import json
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase
from pypdf import PdfWriter

from ColorAdminApp.modules import darpe_library as library


def request(method='get', data=None, level='regional'):
    req = getattr(RequestFactory(), method)('/darpe/biblioteca/documentos/', data=data or {})
    req.session = {'authenticated': True, 'user_id': 'gestor', 'user_profile': {
        'role_id': 2, 'sector': 'D.A.R.P.E', 'access_level': level, 'municipio': 'ITAPEVI',
    }}
    return req


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    stream = io.BytesIO()
    writer.write(stream)
    return SimpleUploadedFile('orientacao.pdf', stream.getvalue(), content_type='application/pdf')


class DarpeLibraryTests(SimpleTestCase):
    def test_valid_pdf(self):
        self.assertTrue(library.validate_pdf(pdf()).startswith(b'%PDF-'))

    def test_rejects_fake_and_encrypted_pdf(self):
        for upload in [SimpleUploadedFile('x.pdf', b'%PDF-invalido'), SimpleUploadedFile('x.html', b'<html>')]:
            with self.assertRaises(ValueError):
                library.validate_pdf(upload)
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.encrypt('senha')
        stream = io.BytesIO(); writer.write(stream)
        with self.assertRaises(ValueError):
            library.validate_pdf(SimpleUploadedFile('x.pdf', stream.getvalue()))

    def _credentials_pdf(self, extra_attachment=False, javascript=False):
        from pypdf.generic import ArrayObject, NameObject
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        writer.add_attachment('Content Credentials', b'provenance metadata')
        spec = writer._root_object['/Names']['/EmbeddedFiles']['/Names'][1].get_object()
        spec[NameObject('/AFRelationship')] = NameObject('/C2PA_Manifest')
        spec['/EF']['/F'][NameObject('/Subtype')] = NameObject('/application/c2pa')
        writer._root_object[NameObject('/AF')] = ArrayObject([spec])
        if extra_attachment:
            writer.add_attachment('anexo.txt', b'not approved')
        if javascript:
            writer.add_js('app.alert("script");')
        stream = io.BytesIO(); writer.write(stream)
        return SimpleUploadedFile('credenciais.pdf', stream.getvalue())

    def test_accepts_passive_content_credentials_without_changing_pdf(self):
        upload = self._credentials_pdf()
        original = upload.read(); upload.seek(0)
        self.assertEqual(library.validate_pdf(upload), original)

    def test_content_credentials_do_not_allow_other_attachments_or_javascript(self):
        for upload in [self._credentials_pdf(extra_attachment=True), self._credentials_pdf(javascript=True)]:
            with self.assertRaises(ValueError):
                library.validate_pdf(upload)

    def test_rejects_attachment_disguised_by_filename_only(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        writer.add_attachment('Content Credentials', b'not c2pa')
        stream = io.BytesIO(); writer.write(stream)
        with self.assertRaises(ValueError):
            library.validate_pdf(SimpleUploadedFile('anexo.pdf', stream.getvalue()))

    def test_unauthenticated_access_denied(self):
        req = request(); req.session = {}
        self.assertEqual(library.documents(req).status_code, 403)
        self.assertEqual(library.download(req, 'uuid').status_code, 403)

    @patch.object(library.requests, 'post')
    def test_local_cannot_publish(self, post):
        self.assertEqual(library.documents(request('post', level='local')).status_code, 403)
        post.assert_not_called()

    @patch('ColorAdminApp.modules.darpe_file_manager.folder', return_value={'id': 'pasta', 'categoria': 'instrumentos'})
    @patch.object(library.requests, 'post')
    def test_upload_pdf_to_private_storage_then_catalog(self, post, folder):
        post.return_value = Mock(ok=True)
        response = library.documents(request('post', {'titulo': 'Orientações', 'categoria': 'instrumentos', 'arquivo': pdf()}))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(post.call_count, 2)
        stored = post.call_args_list[1].kwargs['json']
        self.assertEqual(stored['created_by'], 'gestor')
        self.assertEqual(stored['categoria'], 'instrumentos')

    @patch.object(library, 'allowed', return_value=True)
    @patch.object(library.requests, 'get')
    def test_download_looks_up_record_and_uses_attachment(self, get, allowed):
        get.side_effect = [Mock(json=lambda: [{'object_path': 'safe.pdf', 'original_name': 'Orientação.pdf'}]), Mock(content=b'%PDF-test')]
        response = library.download(request(), 'test')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('/authenticated/darpe-documentos/safe.pdf', get.call_args.args[0])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    @patch.object(library, 'allowed', return_value=True)
    @patch.object(library.requests, 'get')
    def test_preview_is_inline_and_same_origin(self, get, allowed):
        get.side_effect = [Mock(json=lambda: [{'object_path': 'safe.pdf', 'original_name': 'Teste.pdf'}]), Mock(content=b'%PDF-test')]
        response = library.download(request(), 'test', inline=True)
        self.assertTrue(response['Content-Disposition'].startswith('inline;'))
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')

    @patch.object(library, 'allowed', return_value=True)
    @patch.object(library.requests, 'get')
    def test_reader_cannot_preview_archived_pdf(self, get, allowed):
        get.return_value = Mock(json=lambda: [{'object_path': 'safe.pdf', 'original_name': 'Teste.pdf', 'deleted_at': '2026-11-05'}])
        response = library.download(request(level='local'), 'test', inline=True)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(get.call_count, 1)

    @patch.object(library, 'allowed', return_value=True)
    @patch.object(library.requests, 'get')
    def test_preview_revision_is_bound_to_the_document(self, get, allowed):
        get.side_effect = [Mock(json=lambda: [{'object_path': 'safe.pdf', 'original_name': 'Teste.pdf'}]), Mock(json=lambda: [])]
        req = request(); req.GET = {'revision': '00000000-0000-4000-8000-000000000009'}
        self.assertEqual(library.download(req, 'documento', inline=True).status_code, 404)
        self.assertEqual(get.call_args.kwargs['params']['documento_id'], 'eq.documento')

    @patch.object(library, 'allowed', return_value=True)
    @patch.object(library.requests, 'get')
    def test_missing_record_is_404(self, get, allowed):
        get.return_value = Mock(json=lambda: [])
        self.assertEqual(library.download(request(), 'missing').status_code, 404)

    def test_pages_show_four_sectors_and_dated_global_statistics(self):
        # Evita dependência dos menus externos na verificação do conteúdo.
        from django.template.loader import get_template
        html = get_template('pages/darpe_library.html').render({'section': 'setores', 'scope': {}, 'sectors': library.SECTORS})
        self.assertIn('id="stats-period"', html)
        self.assertIn('id="stats-chart"', html)
        self.assertIn('darpe-statistics.js', html)
        self.assertIn('antigo setor 5', html)
        self.assertEqual(len(library.SECTORS), 4)
        rows = {r['name']: r for r in library.instruments()}
        self.assertEqual(rows['Tuba']['s1'], 'Não permitido')
        self.assertEqual(rows['Violino']['s1'], 'Não permitido')
        self.assertIn('ao ar livre', rows['Trompete']['s4'])


class AdditionalFileFormatsTests(SimpleTestCase):
    def test_real_spreadsheet_and_photo(self):
        from openpyxl import Workbook
        from PIL import Image
        for ext in ('xlsx', 'png'):
            stream = io.BytesIO()
            if ext == 'xlsx':
                book = Workbook()
                book.active.append(['Documento', 'Quantidade'])
                book.active.append(['Exemplo', 1])
                book.save(stream)
            else:
                Image.new('RGB', (8, 8), 'white').save(stream, format='PNG')
            data = stream.getvalue()
            self.assertEqual(library.validate_file(SimpleUploadedFile('arquivo.' + ext, data)), data)

    def test_rejects_fake_formats_and_executable(self):
        for name in ('foto.png', 'planilha.xlsx', 'programa.exe'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                library.validate_file(SimpleUploadedFile(name, b'invalid'))

    def test_utf8_text_and_csv(self):
        for name in ('texto.txt', 'dados.csv'):
            data = 'Nome,Quantidade\nExemplo,1'.encode('utf-8')
            self.assertEqual(library.validate_file(SimpleUploadedFile(name, data)), data)
