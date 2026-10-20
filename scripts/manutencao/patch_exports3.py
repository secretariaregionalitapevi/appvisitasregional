import os
import re

files = [
    r'c:\Users\Usuário\OneDrive\APLICATIVOS REGIONAL\DASHBOARD_REGIT\ColorAdminApp\templates\pages\financeiro-lancamentos.html',
    r'c:\Users\Usuário\OneDrive\APLICATIVOS REGIONAL\DASHBOARD_REGIT\ColorAdminApp\templates\pages\financeiro-coletas.html'
]

pdf_new_template = """let sumConstrucao = 0;
let sumPiedade = 0;
let sumManutencao = 0;
let sumMissoes = 0;
let sumEspecial = 0;
let sumArCondicionado = 0;
let sumAssembleia = 0;
let sumPosDebito = 0;
let sumPosPix = 0;
let sumPixAdm = 0;
let sumLivro = 0;
let sumTotal = 0;

const tableData = REPLACE_ARRAY.map(i => {
    const construcao = i.construcao || 0;
    const piedade = i.obra_piedade || 0;
    const manutencao = i.manutencao || 0;
    const missoes = i.viagens_missionarias || 0;
    const especial = i.coleta_especial || 0;
    const ar = i.coleta_ar_condicionado || 0;
    const assembleia = i.assembleia_reuniao || 0;
    const posDebito = i.pos_maquininha || 0;
    const posPix = i.pos_pix || 0;
    const pixAdm = i.pix_adm || 0;
    const livro = i.diversos_piedade || 0;
    const total = i.total || 0;

    sumConstrucao += construcao;
    sumPiedade += piedade;
    sumManutencao += manutencao;
    sumMissoes += missoes;
    sumEspecial += especial;
    sumArCondicionado += ar;
    sumAssembleia += assembleia;
    sumPosDebito += posDebito;
    sumPosPix += posPix;
    sumPixAdm += pixAdm;
    sumLivro += livro;
    sumTotal += total;

    return [
        moment(i.data_coleta).format('DD/MM/YYYY'),
        i.comum,
        formatBRL(construcao),
        formatBRL(piedade),
        formatBRL(manutencao),
        formatBRL(missoes),
        formatBRL(especial),
        formatBRL(ar),
        formatBRL(assembleia),
        formatBRL(posDebito),
        formatBRL(posPix),
        formatBRL(pixAdm),
        formatBRL(livro),
        formatBRL(total)
    ];
});

tableData.push([
    { content: 'TOTAL GERAL', colSpan: 2, styles: { halign: 'center', fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumConstrucao > 0 ? formatBRL(sumConstrucao) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumPiedade > 0 ? formatBRL(sumPiedade) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumManutencao > 0 ? formatBRL(sumManutencao) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumMissoes > 0 ? formatBRL(sumMissoes) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumEspecial > 0 ? formatBRL(sumEspecial) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumArCondicionado > 0 ? formatBRL(sumArCondicionado) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumAssembleia > 0 ? formatBRL(sumAssembleia) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumPosDebito > 0 ? formatBRL(sumPosDebito) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumPosPix > 0 ? formatBRL(sumPosPix) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumPixAdm > 0 ? formatBRL(sumPixAdm) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumLivro > 0 ? formatBRL(sumLivro) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
    { content: sumTotal > 0 ? formatBRL(sumTotal) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } }
]);

doc.autoTable({
    head: [['Data', 'Localidade', 'Construção', 'Piedade BR', 'Manut.', 'Missões', 'Esp. BR', 'Ar Cond.', 'Assemb.', 'Débito', 'PIX', 'PIX ADM', 'Livro', 'Total']],
    body: tableData,
    startY: 42,
    theme: 'striped',
    headStyles: { fillColor: [30, 75, 122], textColor: 255, fontStyle: 'bold', halign: 'center', fontSize: 6 },
    bodyStyles: { fontSize: 6 },
    alternateRowStyles: { fillColor: [245, 248, 250] },
    columnStyles: {
        0: { halign: 'center', cellWidth: 15 },
        1: { cellWidth: 40 },
        2: { halign: 'right' },
        3: { halign: 'right' },
        4: { halign: 'right' },
        5: { halign: 'right' },
        6: { halign: 'right' },
        7: { halign: 'right' },
        8: { halign: 'right' },
        9: { halign: 'right' },
        10: { halign: 'right' },
        11: { halign: 'right' },
        12: { halign: 'right' },
        13: { halign: 'right', fontStyle: 'bold' }
    },
    didDrawPage: function (data) {"""

def add_indent(text, spaces):
    return '\n'.join((' ' * spaces) + line if line.strip() else line for line in text.split('\n'))

for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    array_name = 'currentLancamentos' if 'currentLancamentos.forEach' in content else 'currentData'
    
    # We find the start of pdf exports
    # Usually it's "let sumConstrucao = 0;" inside exportPDF.
    # To be safe, we look for exportPDF then the let sumConstrucao
    match = re.search(r"const exportPDF = \(\) => \{[\s\S]*?(let sumConstrucao = 0;[\s\S]*?didDrawPage: function \(data\) \{)", content)
    
    if match:
        old_block = match.group(1)
        # Determine indentation level
        indent_match = re.search(r"^(\s+)let sumConstrucao", old_block)
        indent_spaces = len(indent_match.group(1)) if indent_match else 0
        
        new_block = add_indent(pdf_new_template.replace('REPLACE_ARRAY', array_name), indent_spaces).lstrip()
        
        # Add the initial indent to the first line which is lstripped
        new_block = (' ' * indent_spaces) + new_block
        
        content = content.replace(old_block, new_block)
        
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Updated PDF logic in {os.path.basename(fpath)}")
    else:
        print(f"Could not find PDF logic in {os.path.basename(fpath)}")
