"""Gera amostras e imagens de QA para a participação SAM, sem consultar produção."""
from datetime import datetime
from pathlib import Path

import pymupdf as fitz
from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont

from ColorAdminApp.tests.tests_music_events_participation import sample
from ColorAdminApp.modules.music_events_reports import build_excel, build_pdf


def render_sheet(sheet, output):
    """Preview das células reais exportadas, respeitando larguras e alturas."""
    from openpyxl.utils import get_column_letter
    font_path = 'C:/Windows/Fonts/arial.ttf'
    scale = 1.1
    widths = [int(sheet.column_dimensions[get_column_letter(c)].width * 7 * scale)
              for c in range(1, sheet.max_column + 1)]
    heights = [int((sheet.row_dimensions[r].height or 15) * 1.333 * scale)
               for r in range(1, sheet.max_row + 1)]
    image = Image.new('RGB', (sum(widths) + 1, sum(heights) + 1), 'white')
    draw = ImageDraw.Draw(image)
    merged = {str(area.start_cell.coordinate):area for area in sheet.merged_cells.ranges}
    y = 0
    for r, height in enumerate(heights, 1):
        x = 0
        for c, width in enumerate(widths, 1):
            cell = sheet.cell(r, c)
            if cell.coordinate in merged:
                area = merged[cell.coordinate]
                width = sum(widths[area.min_col-1:area.max_col])
            if cell.value is not None:
                fill = '#'+cell.fill.fgColor.rgb[-6:] if cell.fill.fgColor.type == 'rgb' and cell.fill.fgColor.rgb != '00000000' else '#ffffff'
                color = '#'+cell.font.color.rgb[-6:] if cell.font.color and cell.font.color.type == 'rgb' else '#243746'
                font = ImageFont.truetype(font_path, round((cell.font.sz or 11) * 1.333 * scale))
                value = str(cell.value)
                if isinstance(cell.value, (int, float)) and '%' in cell.number_format:
                    value = f'{cell.value*100:.2f}%'
                lines, line = [], ''
                for word in value.split():
                    proposed = (line+' '+word).strip()
                    if draw.textlength(proposed,font=font)>width-12 and line:
                        lines.append(line);line=word
                    else:
                        line=proposed
                lines.append(line)
                step = round(font.size*1.2)
                assert len(lines)*step <= height, f'Texto cortado em {sheet.title}!{cell.coordinate}'
                draw.rectangle((x,y,x+width,y+height),fill=fill,outline='#d8dee5')
                for offset,line in enumerate(lines):
                    tx = x+(width-draw.textlength(line,font=font))/2 if cell.alignment.horizontal=='center' else x+6
                    draw.text((tx,y+(height-len(lines)*step)/2+offset*step),line,fill=color,font=font)
            x += widths[c-1]
        y += height
    image.save(output)


def main():
    data, _, _, _ = sample()
    data['report'] = 'participacao'
    out = Path('tmp/sam-participation-qa')
    out.mkdir(parents=True, exist_ok=True)
    now = datetime(2026, 11, 15, 12, 30)
    (out / 'participacao.pdf').write_bytes(build_pdf(data, 'Validação interna', now))
    (out / 'participacao.xlsx').write_bytes(build_excel(data, 'Validação interna', now))
    with fitz.open(out / 'participacao.pdf') as doc:
        for page in doc:
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(out / f'pagina-{page.number+1}.png')
            assert all(25 <= block[0] and block[2] <= page.rect.width - 25
                       for block in page.get_text('blocks') if block[4].strip()), 'Texto fora da largura útil'
        print(f'PDF validado: {len(doc)} página(s), texto dentro das margens.')
    book = load_workbook(out / 'participacao.xlsx', rich_text=True)
    for index, sheet in enumerate(book, 1):
        assert sheet.max_column == 10
        assert sheet['A1'].fill.fgColor.rgb == '001E4B7A'
        assert sheet['A9'].fill.fgColor.rgb == '001E4B7A'
        assert sheet['G10'].number_format == '0.00%'
        assert sheet['J10'].number_format == '0.00%'
        assert sheet.print_area and sheet.auto_filter.ref
        render_sheet(sheet, out / f'planilha-{index}.png')
        print(f'Excel validado: {sheet.title}, {sheet.max_row} linhas, 10 colunas, cabeçalho e impressão.')


if __name__ == '__main__':
    main()
