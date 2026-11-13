import io
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from openpyxl import load_workbook
from pypdf import PdfReader

from ColorAdminApp import exam_exports, music_exams


class ExamExportTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/musica/exames/exportar/', {'historico': '1'})
        self.request.session = {'user_profile': {'role_id': 1, 'full_name': 'Gestor Teste'}}
        self.rows = [dict(id=str(i), nome_aluno=f'ALUNA DEMONSTRAÇÃO DOS SANTOS {i:02}',
                          municipio='ITAPEVI', comum='BR-22-3206 - JARDIM SANTA RITA II',
                          instrumento='ÓRGÃO', categoria='ORGANISTA', origem='PAINEL',
                          tipo_exame='OFICIALIZAÇÃO', data_exame='2026-11-07', resultado='APROVADO',
                          agenda_evento_titulo='EVENTO NÃO DEVE SER EXPORTADO') for i in range(23)]

    def test_pdf_compact_single_line_history_and_footer(self):
        response = exam_exports.history_pdf(self.request, self.rows)
        pdf = PdfReader(io.BytesIO(response.content))
        self.assertEqual(len(pdf.pages), 1)
        text = pdf.pages[0].extract_text()
        for label in ['CONGREGAÇÃO CRISTÃ NO BRASIL', 'Município', 'Comum',
                      'Exames - Regional Itapevi - 2026', 'Impresso por:', 'Gestor Teste']:
            self.assertIn(label, text)
        self.assertNotIn('Evento da agenda', text)
        self.assertNotIn('EVENTO NÃO DEVE SER EXPORTADO', text)
        self.assertEqual(text.count('APROVADA'), 23)

    def test_pdf_repeats_headings_on_later_pages(self):
        pdf = PdfReader(io.BytesIO(exam_exports.history_pdf(self.request, self.rows * 4).content))
        self.assertGreater(len(pdf.pages), 1)
        for page in pdf.pages:
            text = page.extract_text()
            self.assertIn('CONGREGAÇÃO CRISTÃ NO BRASIL', text)
            self.assertIn('Comum', text)
            self.assertIn('Exames - Regional Itapevi - 2026', text)

    def test_excel_result_styles_columns_and_print_identity(self):
        with patch.object(music_exams, 'can_open_module', return_value=True), \
                patch.object(music_exams, 'fetch_rows', return_value=self.rows), \
                patch.object(music_exams, 'fetch_legacy', return_value=[]):
            response = music_exams.export_excel(self.request)
        workbook = load_workbook(io.BytesIO(response.content), rich_text=True)
        sheet = workbook['Registros Individuais']
        self.assertEqual(sheet['D6'].value, 'Município')
        self.assertEqual(sheet['E6'].value, 'Comum')
        self.assertNotIn('Evento da agenda', [cell.value for cell in sheet[6]])
        self.assertNotIn('Gestor Teste', str(sheet['A4'].value))
        self.assertIn('Secretaria Regional da Música', str(sheet['A4'].value))
        self.assertEqual(sheet['I7'].value, 'APROVADA')
        self.assertTrue(sheet['I7'].font.bold)
        self.assertEqual(sheet['I7'].font.color.rgb, '00087A58')
        self.assertEqual(sheet['I7'].alignment.horizontal, 'center')
        self.assertFalse(sheet['E7'].alignment.wrap_text)
        self.assertTrue(sheet['E7'].alignment.shrink_to_fit)
        self.assertEqual(sheet.oddFooter.left.text, 'Exames - Regional Itapevi - 2026')
        self.assertIn('Gestor Teste', sheet.oddFooter.right.text)
        self.assertEqual(sheet.print_title_rows, '$1:$6')

