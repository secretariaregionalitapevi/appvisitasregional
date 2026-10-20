import os

files = [
    r'c:\Users\Usuário\OneDrive\APLICATIVOS REGIONAL\DASHBOARD_REGIT\ColorAdminApp\templates\pages\financeiro-lancamentos.html',
    r'c:\Users\Usuário\OneDrive\APLICATIVOS REGIONAL\DASHBOARD_REGIT\ColorAdminApp\templates\pages\financeiro-coletas.html'
]

excel_orig = """            ['Data', 'Localidade', 'Construção', 'Obra da Piedade', 'Manutenção', 'Missões', 'Ar Condicionado', 'POS Maquininha', 'Total', 'Responsável']
        ];
        let sumConstrucao = 0;
        let sumPiedade = 0;
        let sumManutencao = 0;
        let sumMissoes = 0;
        let sumArCondicionado = 0;
        let sumPos = 0;
        let sumTotal = 0;

        REPLACE_ARRAY.forEach(i => {
            const construcao = i.construcao || 0;
            const piedade = (i.obra_piedade || 0) + (i.diversos_piedade || 0);
            const manutencao = i.manutencao || 0;
            const missoes = i.viagens_missionarias || 0;
            const ar = i.coleta_ar_condicionado || 0;
            const pos = i.pos_maquininha || 0;
            const total = i.total || 0;

            sumConstrucao += construcao;
            sumPiedade += piedade;
            sumManutencao += manutencao;
            sumMissoes += missoes;
            sumArCondicionado += ar;
            sumPos += pos;
            sumTotal += total;

            rows.push([
                moment(i.data_coleta).format('DD/MM/YYYY'),
                i.comum,
                construcao,
                piedade,
                manutencao,
                missoes,
                ar,
                pos,
                total,
                i.responsavel_nome || ''
            ]);
        });

        // Linha de Totais
        rows.push([
            'TOTAL GERAL',
            '',
            sumConstrucao > 0 ? sumConstrucao : '',
            sumPiedade > 0 ? sumPiedade : '',
            sumManutencao > 0 ? sumManutencao : '',
            sumMissoes > 0 ? sumMissoes : '',
            sumArCondicionado > 0 ? sumArCondicionado : '',
            sumPos > 0 ? sumPos : '',
            sumTotal > 0 ? sumTotal : '',
            ''
        ]);"""

excel_new = """            ['Data', 'Localidade', 'Construção', 'Piedade Nível Brasil', 'Manutenção', 'Viagens Missionárias', 'Coleta Especial Brasil', 'Coleta Especial (Ar Cond)', 'Assembléia/Reunião', 'POS Débito', 'POS PIX', 'PIX ADM', 'Livro de Coletas', 'Total', 'Responsável']
        ];
        let sumConstrucao = 0;
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

        REPLACE_ARRAY.forEach(i => {
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

            rows.push([
                moment(i.data_coleta).format('DD/MM/YYYY'),
                i.comum,
                construcao,
                piedade,
                manutencao,
                missoes,
                especial,
                ar,
                assembleia,
                posDebito,
                posPix,
                pixAdm,
                livro,
                total,
                i.responsavel_nome || ''
            ]);
        });

        // Linha de Totais
        rows.push([
            'TOTAL GERAL',
            '',
            sumConstrucao > 0 ? sumConstrucao : '',
            sumPiedade > 0 ? sumPiedade : '',
            sumManutencao > 0 ? sumManutencao : '',
            sumMissoes > 0 ? sumMissoes : '',
            sumEspecial > 0 ? sumEspecial : '',
            sumArCondicionado > 0 ? sumArCondicionado : '',
            sumAssembleia > 0 ? sumAssembleia : '',
            sumPosDebito > 0 ? sumPosDebito : '',
            sumPosPix > 0 ? sumPosPix : '',
            sumPixAdm > 0 ? sumPixAdm : '',
            sumLivro > 0 ? sumLivro : '',
            sumTotal > 0 ? sumTotal : '',
            ''
        ]);"""

excel_col_orig = """        // Auto-size columns
        ws['!cols'] = [
            { wch: 12 }, { wch: 40 }, { wch: 18 }, { wch: 18 }, { wch: 18 }, 
            { wch: 18 }, { wch: 18 }, { wch: 18 }, { wch: 18 }, { wch: 25 }
        ];"""

excel_col_new = """        // Auto-size columns
        ws['!cols'] = [
            { wch: 12 }, { wch: 40 }, { wch: 15 }, { wch: 18 }, { wch: 15 }, 
            { wch: 20 }, { wch: 20 }, { wch: 22 }, { wch: 18 }, { wch: 15 },
            { wch: 15 }, { wch: 15 }, { wch: 18 }, { wch: 15 }, { wch: 25 }
        ];"""

pdf_orig = """        let sumConstrucao = 0;
        let sumPiedade = 0;
        let sumManutencao = 0;
        let sumMissoes = 0;
        let sumArCondicionado = 0;
        let sumPos = 0;
        let sumTotal = 0;

        const tableData = REPLACE_ARRAY.map(i => {
            const construcao = i.construcao || 0;
            const piedade = (i.obra_piedade || 0) + (i.diversos_piedade || 0);
            const manutencao = i.manutencao || 0;
            const missoes = i.viagens_missionarias || 0;
            const ar = i.coleta_ar_condicionado || 0;
            const pos = i.pos_maquininha || 0;
            const total = i.total || 0;

            sumConstrucao += construcao;
            sumPiedade += piedade;
            sumManutencao += manutencao;
            sumMissoes += missoes;
            sumArCondicionado += ar;
            sumPos += pos;
            sumTotal += total;

            return [
                moment(i.data_coleta).format('DD/MM/YYYY'),
                i.comum,
                formatBRL(construcao),
                formatBRL(piedade),
                formatBRL(manutencao),
                formatBRL(missoes),
                formatBRL(ar),
                formatBRL(pos),
                formatBRL(total)
            ];
        });

        tableData.push([
            { content: 'TOTAL GERAL', colSpan: 2, styles: { halign: 'center', fontStyle: 'bold', fillColor: [240, 240, 240] } },
            { content: sumConstrucao > 0 ? formatBRL(sumConstrucao) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
            { content: sumPiedade > 0 ? formatBRL(sumPiedade) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
            { content: sumManutencao > 0 ? formatBRL(sumManutencao) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
            { content: sumMissoes > 0 ? formatBRL(sumMissoes) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
            { content: sumArCondicionado > 0 ? formatBRL(sumArCondicionado) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
            { content: sumPos > 0 ? formatBRL(sumPos) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } },
            { content: sumTotal > 0 ? formatBRL(sumTotal) : '', styles: { fontStyle: 'bold', fillColor: [240, 240, 240] } }
        ]);

        doc.autoTable({
            head: [['Data', 'Localidade', 'Construção', 'Obra da Piedade', 'Manutenção', 'Missões', 'Ar Condicionado', 'Digital (POS)', 'Total']],
            body: tableData,
            startY: 42,
            theme: 'striped',
            headStyles: { fillColor: [30, 75, 122], textColor: 255, fontStyle: 'bold', halign: 'center' },
            bodyStyles: { fontSize: 8 },
            alternateRowStyles: { fillColor: [245, 248, 250] },
            columnStyles: {
                0: { halign: 'center', cellWidth: 20 },
                1: { cellWidth: 70 },
                2: { halign: 'right' },
                3: { halign: 'right' },
                4: { halign: 'right' },
                5: { halign: 'right' },
                6: { halign: 'right' },
                7: { halign: 'right' },
                8: { halign: 'right', fontStyle: 'bold' }
            },
            didDrawPage: function (data) {"""

pdf_new = """        let sumConstrucao = 0;
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

for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # What is the array name?
    if 'currentLancamentos.forEach' in content:
        array_name = 'currentLancamentos'
    else:
        array_name = 'currentData'

    # Apply exactly matching replacements
    content = content.replace(excel_orig.replace('REPLACE_ARRAY', array_name), excel_new.replace('REPLACE_ARRAY', array_name))
    content = content.replace(excel_col_orig, excel_col_new)
    content = content.replace('C >= 2 && C <= 8', 'C >= 2 && C <= 13')
    content = content.replace(pdf_orig.replace('REPLACE_ARRAY', array_name), pdf_new.replace('REPLACE_ARRAY', array_name))

    # Fix modal fields in financeiro-lancamentos.html
    if 'financeiro-lancamentos' in fpath:
        content = content.replace('<label class="form-label fw-bold small">PIEDADE</label>', '<label class="form-label fw-bold small">PIEDADE NÍVEL BRASIL</label>')
        content = content.replace('<label class="form-label fw-bold small">DIVERSOS PIEDADE</label>', '<label class="form-label fw-bold small">LIVRO DE COLETAS</label>')
        
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Updated {os.path.basename(fpath)}")
