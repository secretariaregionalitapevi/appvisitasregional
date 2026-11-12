from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import Workbook, load_workbook
from openpyxl.cell.rich_text import TextBlock
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from ColorAdminApp.modules.report_identity import RESPONSIBLE, printed_by, workbook_identity


class ReportIdentityTests(SimpleTestCase):
    def test_pdf_printer_label_is_bold_and_user_is_regular(self):
        output = BytesIO()
        canvas = Canvas(output)
        printed_by(canvas, 'João & Silva', 560, page='Página 1 de 1')
        canvas.save()
        spans = []
        PdfReader(BytesIO(output.getvalue())).pages[0].extract_text(
            visitor_text=lambda text, cm, tm, font, size: spans.append((text, str((font or {}).get('/BaseFont', '')))))
        self.assertTrue(any('Impresso por:' in text and 'Bold' in font for text, font in spans))
        self.assertTrue(any('João & Silva' in text and 'Bold' not in font for text, font in spans))

    def test_excel_moves_only_print_metadata_and_keeps_responsible_person_data(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['A4'] = 'Emissão: 12/11/2026 14:30 · Impresso por: João & Silva'
        sheet['A9'] = 'Responsável: Instrutor da turma'
        workbook_identity(workbook, 'João & Silva')
        label = next(part for part in sheet['A4'].value if isinstance(part, TextBlock))
        self.assertEqual(label.text, 'Responsável: ')
        self.assertTrue(label.font.b)
        self.assertIn(RESPONSIBLE, str(sheet['A4'].value))
        self.assertNotIn('João', str(sheet['A4'].value))
        self.assertEqual(sheet['A9'].value, 'Responsável: Instrutor da turma')
        output = BytesIO()
        workbook.save(output)
        loaded = load_workbook(BytesIO(output.getvalue()))
        self.assertEqual(loaded.active.oddFooter.right.text, '&BImpresso por:&B João && Silva')

    def test_excel_retains_scope_after_printer_and_supports_ascii_labels(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['A4'] = 'Emissao: 12/11/2026 14:30 · Responsavel: Operador · Recorte: Itapevi'
        workbook_identity(workbook, 'Operador')
        value = str(sheet['A4'].value)
        self.assertIn('Recorte: Itapevi', value)
        self.assertIn(RESPONSIBLE, value)
        self.assertNotIn('Operador', value)
