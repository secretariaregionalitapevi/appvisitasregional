"""Read exam documents as data; never execute document contents."""
import csv
import io
import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader


def normalized(value):
    from .music_exams import norm
    return norm(value)


def exam_kind(text):
    text = normalized(text)
    if 'OFICIALIZA' in text or 'PRE-AVALIA' in text:
        return 'OFICIALIZAÇÃO'
    if 'CULTO OFICIAL' in text:
        return 'CULTO OFICIAL'
    if re.search(r'\bRJM\b', text):
        return 'RJM'
    if 'EMERGEN' in text or 'TESTE ESPECIAL' in text:
        return 'TESTE EMERGENCIAL'
    if 'TROCA' in text and 'INSTRUMENT' in text:
        return 'TROCA DE INSTRUMENTO'
    return ''


def result_kind(text):
    text = normalized(text)
    if 'REPROVAD' in text or 'RETORNOU' in text:
        return 'RETORNOU AO CICLO'
    if 'APROVAD' in text or text == 'APTO' or text == 'APTA':
        return 'APROVADO'
    if 'AUSENTE' in text:
        return 'AUSENTE'
    return 'AGENDADO'


def read_date(value):
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return ''


def table_rows(rows, title=''):
    kind = exam_kind(title)
    headers = None
    current_date = ''
    output = []
    for row in rows:
        values = [str(v).strip() if v is not None else '' for v in row]
        joined = ' '.join(values)
        keys = [normalized(v) for v in values]
        if any(v in {'NOME', 'ALUNO', 'ALUNO(A)', 'NOME_ALUNO'} for v in keys):
            headers = keys
            continue
        if not any(values):
            continue
        # Section headings, never student names or arbitrary notes, define the type.
        if sum(bool(v) for v in values) <= 2 and exam_kind(joined):
            kind = exam_kind(joined)
            continue
        match = re.search(r'\b\d{2}/\d{2}/\d{4}\b', joined)
        if match and not headers:
            current_date = read_date(match.group())
        if headers:
            record = dict(zip(headers, values))
            def get(*names):
                return next((record[n] for n in names if record.get(n)), '')
            name = get('NOME', 'ALUNO', 'ALUNO(A)', 'NOME_ALUNO')
            common = get('COMUM', 'COMUM_CONGREGACAO', 'CONGREGACAO')
            if not name or not common:
                continue
            output.append(dict(nome=name, comum=common,
                               tipo_exame=exam_kind(get('TIPO', 'EXAME', 'TIPO_EXAME')) or kind,
                               resultado=result_kind(get('RESULTADO', 'OBSERVACAO', 'OBSERVACOES')),
                               data_exame=read_date(get('DATA', 'DATA_EXAME')) or current_date,
                               categoria='ORGANISTA' if 'ORGANISTA' in normalized(get('CATEGORIA', 'CARGO', 'CARGO_MINISTERIO')) else '',
                               instrumento=get('INSTRUMENTO'),
                               encarregado_local=get('INSTRUTORA', 'NOME DA INSTRUTORA', 'ENCARREGADO LOCAL')))
        elif len(values) >= 6 and re.fullmatch(r'\d+(?:\.0)?', values[0]) and values[1]:
            output.append(dict(nome=values[1], comum=values[3], instrumento=values[2],
                               encarregado_local=values[4], resultado=result_kind(values[5]),
                               tipo_exame=kind, data_exame=current_date))
    return output


def text_rows(text):
    """Layout-preserving extraction keeps headings above their respective rows."""
    kind = ''
    category = 'ORGANISTA' if 'ORGANISTA' in normalized(text) else ''
    output = []
    for line in text.splitlines():
        line = re.sub(r'\bBR\s*[-–]\s*(\d{2})\s*[-–]\s*(\d+)', r'BR-\1-\2', line, flags=re.I)
        if not re.search(r'BR-\d{2}-\d+', line, re.I):
            kind = exam_kind(line) or kind
            continue
        match = re.match(r'\s*(?:\d+\s*)?(.+?)\s+(BR-\d{2}-\d+.*)', line, re.I)
        if not match:
            continue
        name, tail = match.groups()
        parts = re.split(r'\s{2,}|\t', tail.strip())
        # Without column boundaries only the unique common code is safe to infer.
        common = parts[0] if len(parts) > 1 else re.match(r'BR-\d{2}-\d+', tail, re.I).group()
        output.append(dict(nome=name.strip(), comum=common, tipo_exame=kind,
                           categoria=category,
                           resultado=result_kind(tail), data_exame='', instrumento='',
                           encarregado_local=parts[1] if len(parts) > 2 else ''))
    return output


def ocr_image(content):
    from PIL import Image, ImageOps
    import os
    import subprocess
    import tempfile
    from django.conf import settings
    image = Image.open(io.BytesIO(content))
    if image.width * image.height > 40_000_000:
        raise ValueError('Imagem muito grande. Limite: 40 megapixels.')
    image = ImageOps.exif_transpose(image).convert('RGB')
    if os.name == 'nt' and not getattr(settings, 'EXAM_TESSERACT_CMD', ''):
        # Use the operating system OCR without sending student data to a service.
        script = Path(__file__).resolve().parents[2] / 'scripts' / 'exam_windows_ocr.ps1'
        with tempfile.TemporaryDirectory(prefix='exam-ocr-') as directory:
            path = Path(directory) / 'image.png'
            if max(image.size) > 2600:
                image.thumbnail((2600, 2600))
            image.save(path)
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(script), '-ImagePath', str(path)], capture_output=True, timeout=60,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                return result.stdout.decode('utf-8-sig')
    import pytesseract
    command = getattr(settings, 'EXAM_TESSERACT_CMD', '')
    if command:
        pytesseract.pytesseract.tesseract_cmd = command
    try:
        return pytesseract.image_to_string(image, lang=getattr(settings, 'EXAM_OCR_LANG', 'por'),
                                           config='--psm 6 -c preserve_interword_spaces=1', timeout=45)
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError) as exc:
        raise ValueError('OCR indisponível. Instale Tesseract com idioma português ou envie Excel/PDF com texto.') from exc


def read_document(file):
    if file.size > 12 * 1024 * 1024:
        raise ValueError('O arquivo deve ter no máximo 12 MB.')
    extension = Path(file.name).suffix.lower()
    if extension == '.xlsx':
        workbook = load_workbook(file, read_only=True, data_only=True)
        try:
            for sheet in workbook:
                if sheet.max_row is None or sheet.max_column is None:
                    sheet.calculate_dimension(force=True)
            if sum(s.max_row * s.max_column for s in workbook) > 200_000:
                raise ValueError('Planilha muito grande. Limite: 200 mil células.')
            # GERAL duplicates the stage-specific tabs in the supplied workbook.
            stages = [s for s in workbook if exam_kind(s.title)]
            return [r for sheet in (stages or workbook.worksheets)
                    for r in table_rows(sheet.iter_rows(values_only=True), sheet.title)]
        finally:
            workbook.close()
    if extension in {'.csv', '.tsv', '.txt'}:
        raw = file.read()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp1252')
        if extension == '.txt':
            return text_rows(text)
        delimiter = '\t' if extension == '.tsv' else csv.Sniffer().sniff(text[:8192], delimiters=',;\t').delimiter
        return table_rows(csv.reader(io.StringIO(text), delimiter=delimiter))
    if extension == '.pdf':
        reader = PdfReader(file)
        if len(reader.pages) > 30:
            raise ValueError('PDF limitado a 30 páginas por importação.')
        output = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text(extraction_mode='layout') or ''
            if not text.strip():
                import pypdfium2 as pdfium
                file.seek(0)
                pdf = pdfium.PdfDocument(file.read())
                try:
                    image = pdf[index].render(scale=2).to_pil()
                    buffer = io.BytesIO()
                    image.save(buffer, format='PNG')
                    text = ocr_image(buffer.getvalue())
                finally:
                    pdf.close()
            output.extend(text_rows(text))
        return output
    if extension in {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp'}:
        return text_rows(ocr_image(file.read()))
    raise ValueError('Formato não suportado. Use PDF, XLSX, CSV, TSV, TXT ou imagem.')
