"""Institutional responsibility and authenticated printing attribution."""
from html import escape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

RESPONSIBLE = 'Secretaria Regional da Música'
RESPONSIBLE_HTML = '<b>Responsável:</b> ' + RESPONSIBLE


def printed_by(canvas, actor, right, y=16, page='', width=320, size=7):
    """Right aligned, with only the label bold; retains a single footer line."""
    suffix = (' - ' + page) if page else ''
    text = '<b>Impresso por:</b> ' + escape(str(actor)) + escape(suffix)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    measured = (stringWidth('Impresso por: ', 'Helvetica-Bold', size)
                + stringWidth(str(actor) + suffix, 'Helvetica', size))
    fitted = min(size, size * width / max(measured, 1))
    paragraph = Paragraph(text, ParagraphStyle('printed-by', fontName='Helvetica',
                          fontSize=fitted, leading=fitted, alignment=2,
                          textColor='#526371'))
    paragraph.wrap(width, 20)
    paragraph.drawOn(canvas, right - width, y - 1)


def workbook_identity(workbook, actor):
    """Move only report metadata, preserving operational responsible-person columns."""
    import re
    from copy import copy
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    for sheet in workbook:
        found = False
        emission = None
        for row in sheet.iter_rows(max_row=min(7, sheet.max_row)):
            for cell in row:
                value = cell.value
                if isinstance(value, str) and re.search(r'emiss[aã]o\s*:', value, re.I):
                    emission = cell
                if not isinstance(value, str) or not re.search(r'(?:impresso por|respons[aá]vel)\s*:', value, re.I):
                    continue
                found = True
                prefix, old = re.split(r'(?:impresso por|respons[aá]vel)\s*:', value, maxsplit=1, flags=re.I)
                prefix = re.sub(r'</?b>', '', prefix)
                # Keep additional scope/count metadata following the old user name.
                suffix = (' · ' + old.split(' · ', 1)[1]) if ' · ' in old else ''
                cell.value = CellRichText(prefix, TextBlock(InlineFont(b=True), 'Responsável: '), RESPONSIBLE + suffix)
                font = copy(cell.font)
                font.bold = False
                cell.font = font
        if not found and emission is not None:
            text = str(emission.value).replace(' · ' + RESPONSIBLE, '')
            emission.value = CellRichText(text + ' · ', TextBlock(InlineFont(b=True), 'Responsável: '), RESPONSIBLE)
        for footer in (sheet.oddFooter, sheet.evenFooter, sheet.firstFooter):
            footer.right.text = '&BImpresso por:&B ' + str(actor).replace('&', '&&')
