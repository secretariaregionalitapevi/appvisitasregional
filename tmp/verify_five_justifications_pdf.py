from pathlib import Path
import pymupdf

source = Path('output/pdf/presenca_encarregados_identificados_15_11_2026.pdf')
target = Path('output/pdf/encarregados_15_11_2026_5_justificativas.pdf')
pdf = pymupdf.open(source)
text = '\n'.join(page.get_text() for page in pdf)
names = ['AMARILDO PEREIRA DOMINGUES', 'ELCIO MONTEIRO REIS', 'MICHEL FRANK BONFIM CHAVES',
         'NATANAEL ZANIN', 'DIOGO LUCAS DE CAMARGO']
for name in names:
    assert text.count('Encarregado: ' + name) == 1, name
    status = text.split('Encarregado: ' + name, 1)[1].split('15/11/2026', 1)[0]
    assert 'JUSTIFICOU' in status, (name, status)
target.write_bytes(source.read_bytes())
for index, page in enumerate(pdf):
    if 'MICHEL FRANK BONFIM CHAVES' in page.get_text():
        page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save('tmp/pdfs/michel-justificou-confirmado.png')
        print('Página de Michel:', index + 1)
print('Cinco pessoas únicas; as cinco justificativas confirmadas no PDF entregue.')
