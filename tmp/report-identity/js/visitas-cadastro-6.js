
        const userName = 'null';
        const CAN_VIEW_RESTRICTED_NOTES = null;
        let irmandadeData = [];
        let agendaData = [];
        const CADASTRO_ACCESS_LEVEL = 'null';
        const CADASTRO_DEFAULT_COMMON = 'null';
        const CADASTRO_DEFAULT_CITY = 'null';
        const CADASTRO_COMMONS = JSON.parse(document.getElementById('cadastro-commons-data')?.textContent || '[]');
        let cadastroSelectedCity = CADASTRO_DEFAULT_CITY;
        let cadastroSelectedCommon = CADASTRO_DEFAULT_COMMON;
        let searchAcrossCommons = false;
        const INITIAL_IRMANDADE_SEARCH = new URLSearchParams(window.location.search).get('q') || '';
        const escapeHtml = value => $('<div>').text(String(value ?? '')).html();
        const compareMembersByName = (left, right) => String(left?.nome || '')
            .trim().replace(/\s+/g, ' ')
            .localeCompare(String(right?.nome || '').trim().replace(/\s+/g, ' '), 'pt-BR', {
                sensitivity: 'base',
                numeric: true
            });

        // Inicialização Profissional
        const loadContent = async ({ allCommons = searchAcrossCommons } = {}) => {
            moment.locale('pt-br');
            if (!cadastroSelectedCommon && !allCommons) {
                irmandadeData = [];
                agendaData = [];
                updateWidgets([]);
                updateSelects();
                renderItems([]);
                $('#exec-text').html('<b>Selecione uma comum</b> para visualizar os membros cadastrados.');
                return;
            }
            try {
                const commonQuery = allCommons ? 'all' : encodeURIComponent(cadastroSelectedCommon);
                const [resIrm, resAge] = await Promise.all([
                    fetch(`/visitas/api/irmandade/?comum=${commonQuery}`),
                    // A pesquisa global precisa ampliar somente os membros.
                    // A agenda permanece no escopo da comum selecionada para
                    // evitar uma carga desnecessária e preservar servidores
                    // que ainda não aceitam o marcador "all" nessa API.
                    fetch(`/visitas/api/agenda/?comum=${encodeURIComponent(cadastroSelectedCommon)}`)
                ]);
                
                const irmandadePayload = await resIrm.json();
                const agendaPayload = await resAge.json();
                if (!resIrm.ok || !Array.isArray(irmandadePayload)) {
                    throw new Error(irmandadePayload.error || 'Não foi possível carregar os membros.');
                }
                if (!resAge.ok || !Array.isArray(agendaPayload)) {
                    throw new Error(agendaPayload.error || 'Não foi possível carregar a agenda.');
                }
                irmandadeData = [...irmandadePayload].sort(compareMembersByName);
                agendaData = agendaPayload;
                
                updateWidgets(irmandadeData);
                updateSelects();
                const searchInput = document.getElementById('irmandade-search');
                if (searchInput && INITIAL_IRMANDADE_SEARCH && !searchInput.value) {
                    searchInput.value = INITIAL_IRMANDADE_SEARCH;
                }
                handleSearch(searchInput?.value || '');
            } catch (err) {
                console.error("Erro ao carregar dados:", err);
            }
        };

        const EXPORT_COLUMNS = [
            ['nome', 'Nome completo'], ['comum', 'Comum'], ['codigo_comum', 'Código da comum'], ['cidade', 'Cidade'], ['status', 'Status'],
            ['cargo_ministerio', 'Cargo / Ministério'], ['setor', 'Bairro / Setor'], ['endereco_limpo', 'Endereço'],
            ['complemento', 'Complemento'], ['cep', 'CEP'], ['latitude', 'Latitude'], ['longitude', 'Longitude'],
            ['celular_formatado', 'Celular'], ['preferencia_periodo_visita', 'Preferência de período de visita'], ['ultima_visita', 'Última visita'],
            ['frequencia_visita', 'Frequência de visita'], ['data_nascimento', 'Data de nascimento'],
            ['data_batismo', 'Data de batismo'], ['data_inicio_ensaios', 'Início nos ensaios'],
            ['data_culto_oficial', 'Culto oficial'], ['data_oficializacao', 'Oficialização'], ['familia', 'Família'],
            ['id_chefe_familia', 'ID chefe da família'], ['vinculo_tipo', 'Vínculo familiar'], ['categoria', 'Categoria'],
            ['equipe_visita', 'Equipe de visita'], ['classificacao_adicional', 'Classificação adicional'], ['observacoes', 'Observações'],
            ...(CAN_VIEW_RESTRICTED_NOTES ? [['apontamentos_restritos', 'Apontamentos restritos']] : []),
            ['referencia_geografica', 'Referência geográfica'], ['url_foto', 'URL da foto'],
            ['origem_registro', 'Origem do registro'], ['data_cadastro', 'Data do cadastro'],
            ['created_at', 'Data do registro'], ['updated_at', 'Data da atualização'], ['id', 'ID do sistema']
        ];
        const cargoMinisterio = item => {
            const values = (item.cargo_outros || '').split(',').map(v => v.trim()).filter(Boolean);
            [['perfil_musico','Músico'],['cargo_organista','Organista'],['perfil_mocidade','Mocidade'],['perfil_enfermo','Enfermo'],['cargo_porteiro','Porteiro'],['cargo_auxiliar_porta','Auxiliar da Porta'],['cargo_cozinha','Cozinha'],['cargo_limpeza','Limpeza']].forEach(([key,label]) => { if (item[key]) values.push(label); });
            return [...new Set(values)].join(', ') || '-';
        };
        const normalizeHouseAddress = value => String(value || '')
            .replace(/^\s*\[[^\]]+\]\s*/, '')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
        const formatCellPhone = value => {
            let digits = String(value || '').replace(/\D/g, '');
            if (digits.length === 13 && digits.startsWith('55')) digits = digits.slice(2);
            if (digits.length === 11) return `(${digits.slice(0,2)}) ${digits[2]} ${digits.slice(3,7)}-${digits.slice(7)}`;
            if (digits.length === 10) return `(${digits.slice(0,2)}) ${digits.slice(2,6)}-${digits.slice(6)}`;
            return digits;
        };
        const formatBrazilianDateTime = value => value && moment(value).isValid() ? moment(value).format('DD/MM/YYYY HH:mm') : (value || '');
        const formatBrazilianDate = value => value && moment(value).isValid() ? moment(value).format('DD/MM/YYYY') : (value || '');
        const exportRecord = item => {
            const match = String(item.endereco || '').match(/^\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]\s*(.*)$/);
            const commonCode = String(item.codigo_comum || item.comum || '').toUpperCase().match(/BR-\d{2}-\d{3,4}/)?.[0] || '';
            return {...item,
                codigo_comum: commonCode,
                cargo_ministerio: cargoMinisterio(item),
                celular_formatado: formatCellPhone(item.celular || item.telefone),
                latitude: match ? Number(match[1]) : '', longitude: match ? Number(match[2]) : '',
                endereco_limpo: match ? match[3] : (item.endereco || ''),
                ultima_visita: formatBrazilianDateTime(item.ultima_visita),
                data_nascimento: formatBrazilianDate(item.data_nascimento), data_batismo: formatBrazilianDate(item.data_batismo),
                data_inicio_ensaios: formatBrazilianDate(item.data_inicio_ensaios), data_culto_oficial: formatBrazilianDate(item.data_culto_oficial),
                data_oficializacao: formatBrazilianDate(item.data_oficializacao),
                data_cadastro: formatBrazilianDateTime(item.data_cadastro), created_at: formatBrazilianDateTime(item.created_at),
                updated_at: formatBrazilianDateTime(item.updated_at)
            };
        };
        const getAllExportRecords = async () => {
            if (!cadastroSelectedCommon) throw new Error('Selecione uma comum antes de exportar.');
            const response = await fetch(`/visitas/api/irmandade/?export=1&comum=${encodeURIComponent(cadastroSelectedCommon)}`);
            const data = await response.json();
            if (!response.ok || !Array.isArray(data)) throw new Error(data.error || 'Não foi possível carregar os registros.');
            return data.map(exportRecord);
        };

        const exportExcel = async () => {
            const dataDe = $('#peridodo-de').val();
            const dataAte = $('#peridodo-ate').val();
            const periodText = dataDe && dataAte ? `${moment(dataDe).format('DD/MM/YYYY')} a ${moment(dataAte).format('DD/MM/YYYY')}` : 'Todos os registros';

            const rows = [
                ['Congregação Cristã no Brasil'],
                ['Regional Itapevi - São Paulo'],
                ['CADASTRO DE IRMANDADE'],
                ['Relatório Detalhado de Membros'],
                ['Período', periodText],
                ['Responsável', 'Secretaria Regional da Música'],
                ['Impresso em', `${moment().format('DD/MM/YYYY')} às ${moment().format('HH:mm')}`],
                [],
                ['Membro', 'Localidade', 'Cargos / Ministério', 'Status']
            ];

            try {
                Swal.fire({title: 'Preparando Excel...', allowOutsideClick: false, didOpen: () => Swal.showLoading()});
                const records = await getAllExportRecords();
                rows[8] = EXPORT_COLUMNS.map(([, label]) => label);
                records.forEach(item => rows.push(EXPORT_COLUMNS.map(([key]) => item[key] ?? '')));

            rows.push([],['Impresso por:',userName]);
            const ws = XLSX.utils.aoa_to_sheet(rows);
            
            const range = XLSX.utils.decode_range(ws['!ref']);
            for (let R = range.s.r; R <= range.e.r; ++R) {
                for (let C = range.s.c; C <= range.e.c; ++C) {
                    const cell_ref = XLSX.utils.encode_cell({c: C, r: R});
                    if (!ws[cell_ref]) continue;

                    // Header row (index 8)
                    if (R === 8) {
                        ws[cell_ref].s = { font: { bold: true }, alignment: { horizontal: 'center' } };
                    }
                }
            }

            ws['!cols'] = EXPORT_COLUMNS.map(([, label]) => ({wch: Math.min(45, Math.max(14, label.length + 3))}));
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, "Irmandade");
            XLSX.writeFile(wb, "Cadastro_Irmandade.xlsx");
                Swal.close();
            } catch (error) {
                Swal.fire('Erro na exportação', error.message, 'error');
            }
        };

        const exportPDF = async () => {
            const { jsPDF } = window.jspdf;
            const doc = new jsPDF();
            const pageWidth = doc.internal.pageSize.getWidth();
            
            const dataDe = $('#peridodo-de').val();
            const dataAte = $('#peridodo-ate').val();
            const periodText = dataDe && dataAte ? `${moment(dataDe).format('DD/MM/YYYY')} a ${moment(dataAte).format('DD/MM/YYYY')}` : 'Todos os registros';

            doc.setFontSize(16);
            doc.setFont('helvetica', 'bold');
            doc.text('CONGREGAÇÃO CRISTÃ NO BRASIL', pageWidth / 2, 15, { align: 'center' });
            
            doc.setFontSize(10);
            doc.setFont('helvetica', 'normal');
            doc.text('Regional Itapevi - São Paulo', pageWidth / 2, 21, { align: 'center' });
            
            doc.setFontSize(12);
            doc.setFont('helvetica', 'bold');
            doc.setTextColor(30, 75, 122);
            doc.text('CADASTRO DE IRMANDADE', pageWidth / 2, 29, { align: 'center' });
            
            doc.setFontSize(10);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(100, 100, 100);
            doc.text('Relatório Detalhado de Membros', pageWidth / 2, 34, { align: 'center' });

            doc.setFontSize(8);
            doc.setTextColor(0, 0, 0);
            doc.text(`Emissão: ${moment().format('DD/MM/YYYY')}`, pageWidth - 14, 15, { align: 'right' });
            doc.text(`Período: ${periodText}`, pageWidth - 14, 20, { align: 'right' });
            window.AppReportIdentity.jsPdfHeader(doc,pageWidth-14,25);
            
            doc.setFontSize(7);
            doc.setTextColor(100, 100, 100);
            doc.text(`${moment().format('DD/MM/YYYY')} às ${moment().format('HH:mm')}`, pageWidth - 14, 29, { align: 'right' });

            Swal.fire({title: 'Preparando PDF...', allowOutsideClick: false, didOpen: () => Swal.showLoading()});
            let pdfRecords;
            try { pdfRecords = await getAllExportRecords(); } catch (error) {
                return Swal.fire('Erro na exportação', error.message, 'error');
            }
            Swal.close();
            const headers = [["Membro", "Comum", "Cargo / Ministério", "Celular", "Última visita", "Status"]];
            const tableData = pdfRecords.map(i => [
                i.nome,
                i.comum || 'Comum nao informada',
                i.cargo_ministerio,
                i.celular_formatado || '-',
                i.ultima_visita || '-',
                i.status || 'Ativo'
            ]);

            doc.autoTable({
                head: headers,
                body: tableData,
                startY: 40,
                styles: { fontSize: 8 },
                headStyles: { fillColor: [30, 75, 122], textColor: 255 },
                alternateRowStyles: { fillColor: [245, 245, 245] },
                didDrawPage: function (data) {
                    doc.setFontSize(8);
                    doc.text(`Página ${data.pageNumber}`, pageWidth - 14, 10, { align: 'right' });
                }
            });

            window.AppReportIdentity.jsPdfFooter(doc,userName);doc.save("Cadastro_Irmandade.pdf");
        };

        const MATRIX_COLUMNS = [
            ['nome','Nome completo'], ['comum','Comum'], ['codigo_comum','Código da comum'], ['cidade','Cidade'], ['status','Status'],
            ['cargo_outros','Cargo / Ministério'], ['setor','Bairro / Setor'], ['endereco','Endereço'],
            ['complemento','Complemento'], ['cep','CEP'], ['latitude','Latitude'], ['longitude','Longitude'],
            ['celular','Celular'], ['preferencia_periodo_visita','Preferência de período de visita'], ['ultima_visita','Última visita'],
            ['frequencia_visita','Frequência de visita'], ['data_nascimento','Data de nascimento'],
            ['data_batismo','Data de batismo'], ['data_inicio_ensaios','Início nos ensaios'],
            ['data_culto_oficial','Culto oficial'], ['data_oficializacao','Oficialização'], ['familia','Família'],
            ['id_chefe_familia','ID chefe da família'], ['vinculo_tipo','Vínculo familiar'], ['categoria','Categoria regional'],
            ['equipe_visita','Equipe de visita'], ['classificacao_adicional','Classificação adicional'], ['observacoes','Observações'],
            ...(CAN_VIEW_RESTRICTED_NOTES ? [['apontamentos_restritos','Apontamentos']] : []),
            ['referencia_geografica','Referência geográfica'], ['url_foto','URL da foto']
        ];
        const downloadMatrix = () => {
            const headers = MATRIX_COLUMNS.map(([, label]) => label);
            const ws = XLSX.utils.aoa_to_sheet([headers]);
            ws['!cols'] = headers.map(h => ({wch: Math.min(42, Math.max(16, h.length + 3))}));
            const instructions = XLSX.utils.aoa_to_sheet([
                ['PLANILHA MATRIZ - CADASTRO DA IRMANDADE'],
                ['Preencha uma pessoa por linha. Não altere os títulos das colunas.'],
                ['Nome completo e Comum são obrigatórios. Latitude e Longitude devem ser números decimais.'],
                ['Cargo / Ministério: informe múltiplos cargos separados por vírgula.'],
                ['Status sugeridos: Ativo ou Inativo. Datas: DD/MM/AAAA ou AAAA-MM-DD.'],
                ['Categoria regional: use somente GVI, GVM, GVE, RF ou RE.'],
                ['Classificação adicional: use para Avivamento, Resgate e outras classificações locais.'],
                [],
                ['EXEMPLOS DE PREENCHIMENTO'],
                ['Campo', 'Exemplo'],
                ['Comum', 'BR-22-0673 - VILA DOUTOR CARDOSO'],
                ['Código da comum', 'BR-22-0673'],
                ['Cidade', 'Itapevi'],
                ['Celular', '(11) 9 1234-5678'],
                ['Preferência de período de visita', 'Manhã ou Tarde'],
                ['Cargo / Ministério', 'Músico, Grupo de Visitas'],
                ['Data', '06/08/2026']
            ]);
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, 'Cadastro');
            XLSX.utils.book_append_sheet(wb, instructions, 'Instruções');
            XLSX.writeFile(wb, 'Planilha_Matriz_Irmandade.xlsx');
        };
        const importCSV = () => { const input = document.getElementById('import-file'); input.value = ''; input.click(); };
        const normalizeHeader = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
        const friendlyImportError = (result, start, end) => {
            const raw = typeof result?.details === 'string' ? result.details : JSON.stringify(result?.details || result || {});
            let parsed = {};
            try { parsed = JSON.parse(raw); } catch (_) {}
            const code = parsed.code || result?.code || '';
            const message = String(parsed.message || result?.error || raw || '').toLowerCase();
            const batch = `linhas ${start + 2} a ${end + 1}`;
            if (code === '22P02' || message.includes('uuid')) return `Há um vínculo familiar inválido nas ${batch}. Deixe “ID chefe da família” vazio ou informe um ID válido do sistema.`;
            if (code === '23505' || message.includes('duplicate')) return `Um ou mais membros das ${batch} já estão cadastrados. Revise possíveis duplicidades.`;
            if (code === '23502' || message.includes('not-null')) return `Falta uma informação obrigatória nas ${batch}. Confira principalmente Nome completo e Comum.`;
            if (code === '23514' || message.includes('check constraint')) return `Um valor das ${batch} não atende às opções permitidas pelo sistema. ${parsed.message || ''}`.trim();
            if (code === 'PGRST102' || message.includes('object keys')) return `As linhas da planilha possuem estruturas diferentes nas ${batch}. O sistema já tentou uniformizá-las; atualize a página e repita a importação.`;
            if (code === '22007' || message.includes('date')) return `Há uma data inválida nas ${batch}. Utilize o formato dd/mm/aaaa.`;
            if (code === 'PGRST204' || message.includes('schema cache')) return 'A estrutura da planilha não corresponde à versão atual do sistema. Atualize a página e tente novamente.';
            if (code === '42501' || message.includes('permission')) return 'Seu usuário não possui permissão para importar registros nessa localidade.';
            return `Não foi possível importar as ${batch}. Revise os dados preenchidos e tente novamente.`;
        };
        const processImport = async file => {
            if (!file) return;
            try {
                const workbook = XLSX.read(await file.arrayBuffer(), {type:'array', cellDates:true});
                const rows = XLSX.utils.sheet_to_json(workbook.Sheets[workbook.SheetNames[0]], {defval:'', raw:false});
                const headerMap = new Map(MATRIX_COLUMNS.map(([key,label]) => [normalizeHeader(label), key]));
                // Compatibilidade com planilhas antigas: valores regionais permanecem em
                // categoria; valores como Avivamento/Resgate são movidos abaixo para a classificação adicional.
                headerMap.set(normalizeHeader('Categoria'), 'categoria');
                if (CAN_VIEW_RESTRICTED_NOTES) {
                    ['Apontamentos', 'Apontamento', 'Observações restritas', 'Observação restrita'].forEach(label => {
                        headerMap.set(normalizeHeader(label), 'apontamentos_restritos');
                    });
                }
                // As planilhas das comuns nem sempre usam o título extenso da matriz.
                // Todos estes cabeçalhos representam o mesmo campo de preferência.
                ['Período', 'Periodo', 'Período da visita', 'Turno', 'Preferência de período'].forEach(label => {
                    headerMap.set(normalizeHeader(label), 'preferencia_periodo_visita');
                });
                const records = rows.map((row, rowIndex) => {
                    const item = {};
                    Object.entries(row).forEach(([header,value]) => { const key = headerMap.get(normalizeHeader(header)); if (key) item[key] = value; });
                    const lat = String(item.latitude || '').replace(',', '.'); const lng = String(item.longitude || '').replace(',', '.');
                    if ((lat && !lng) || (!lat && lng)) throw new Error(`Preencha Latitude e Longitude juntas na linha ${rowIndex + 2}.`);
                    if (lat && lng) item.endereco = `[${lat}, ${lng}] ${item.endereco || ''}`;
                    delete item.latitude; delete item.longitude;
                    const code = String(item.codigo_comum || item.comum || '').toUpperCase().match(/BR-\d{2}-\d{3,4}/)?.[0] || '';
                    item.codigo_comum = code;
                    if (code && !String(item.comum || '').toUpperCase().startsWith(code)) item.comum = `${code} - ${item.comum || ''}`.trim();
                    item.celular = formatCellPhone(item.celular);
                    if (item.preferencia_periodo_visita) {
                        const periodo = normalizeHeader(item.preferencia_periodo_visita);
                        const isManha = /(^|\s)manha(\s|$)/.test(periodo);
                        const isTarde = /(^|\s)tarde(\s|$)/.test(periodo);
                        if (isManha === isTarde) throw new Error(`A “Preferência de período de visita” está inválida na linha ${rowIndex + 2}. Use Manhã ou Tarde.`);
                        item.preferencia_periodo_visita = isManha ? 'Manhã' : 'Tarde';
                    }
                    ['ultima_visita','data_nascimento','data_batismo','data_inicio_ensaios','data_culto_oficial','data_oficializacao'].forEach(key => {
                        if (!item[key]) { delete item[key]; return; }
                        const parsed = moment(item[key], ['DD/MM/YYYY','YYYY-MM-DD','DD-MM-YYYY'], true);
                        if (!parsed.isValid()) throw new Error(`A data da coluna “${MATRIX_COLUMNS.find(([field]) => field === key)?.[1] || key}” está inválida na linha ${rowIndex + 2}. Use dd/mm/aaaa.`);
                        item[key] = parsed.format('YYYY-MM-DD');
                    });
                    if (item.id_chefe_familia) {
                        const familyId = String(item.id_chefe_familia).trim();
                        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(familyId)) throw new Error(`O “ID chefe da família” está inválido na linha ${rowIndex + 2}. Deixe vazio ou copie um ID válido do sistema.`);
                        item.id_chefe_familia = familyId;
                    } else {
                        delete item.id_chefe_familia;
                    }
                    const cargos = String(item.cargo_outros || '').split(',').map(value => value.trim()).filter(Boolean);
                    const hasCargo = label => cargos.some(value => normalizeHeader(value) === normalizeHeader(label));
                    item.perfil_musico = hasCargo('Músico'); item.cargo_organista = hasCargo('Organista');
                    item.perfil_mocidade = hasCargo('Mocidade');
                    item.perfil_enfermo = hasCargo('Enfermo'); item.cargo_porteiro = hasCargo('Porteiro');
                    item.cargo_auxiliar_porta = hasCargo('Auxiliar da Porta'); item.cargo_cozinha = hasCargo('Cozinha'); item.cargo_limpeza = hasCargo('Limpeza');
                    item.status = item.status || 'Ativo'; item.cargo_outros = cargos.join(',');
                    if (item.categoria) {
                        const categoriaOriginal = String(item.categoria).trim();
                        const categoria = categoriaOriginal.toUpperCase();
                        if (['GVI', 'GVM', 'GVE', 'RF', 'RE'].includes(categoria)) {
                            item.categoria = categoria;
                        } else {
                            item.classificacao_adicional = [item.classificacao_adicional, categoriaOriginal].filter(Boolean).join(', ');
                            delete item.categoria;
                        }
                    }
                    Object.keys(item).forEach(key => {
                        if (typeof item[key] === 'string') item[key] = item[key].trim();
                        if (item[key] === '') delete item[key];
                    });
                    return item;
                }).filter(item => item.nome && item.comum);
                if (!records.length) throw new Error('Nenhuma linha válida. Preencha ao menos Nome completo e Comum.');
                const confirmation = await Swal.fire({
                    icon:'question', title:`Sincronizar ${records.length} linhas?`,
                    html:'O sistema cadastrará somente nomes novos.<br><small>Quem já estiver cadastrado na mesma comum será preservado sem alterações.</small>',
                    showCancelButton:true, confirmButtonText:'Sincronizar planilha', cancelButtonText:'Cancelar'
                });
                if (!confirmation.isConfirmed) return;
                let createdTotal = 0;
                let updatedTotal = 0;
                let skippedTotal = 0;
                let importNotice = null;
                for (let start=0; start<records.length; start+=250) {
                    importNotice = AppFeedback.show({
                        type: 'loading',
                        flow: 'sync',
                        title: 'Sincronizando planilha',
                        message: `Analisando ${Math.min(start + 250, records.length)} de ${records.length} registros.`
                    });
                    const response = await fetch('/visitas/api/irmandade/?smart=1', {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':'null'}, body:JSON.stringify(records.slice(start,start+250))});
                    const result = await response.json();
                    if (!response.ok) throw new Error(friendlyImportError(result, start, Math.min(start + 250, records.length)));
                    createdTotal += Number(result.created || 0);
                    updatedTotal += Number(result.updated || 0);
                    skippedTotal += Number(result.skipped || 0);
                }
                importNotice?.close();
                await loadContent();
                AppFeedback.show({
                    type: 'success',
                    flow: 'sync',
                    title: 'Sincronização concluída',
                    message: `${createdTotal} novo(s), ${updatedTotal} atualizado(s) e ${skippedTotal} preservado(s).`,
                    detail: 'A planilha foi processada e a lista de irmandade foi atualizada.'
                });
            } catch (error) {
                AppFeedback.close();
                AppFeedback.show({
                    type: 'error',
                    flow: 'sync',
                    title: 'Erro na importação',
                    message: error.message
                });
            }
        };

        const updateWidgets = (data) => {
            const now = moment();
            const last30d = moment().subtract(30, 'days');
            const last60d = moment().subtract(60, 'days');
            const startOfYear = moment().startOf('year');

            // 1. Famílias Assistidas (30d) - Lógica de Consolidação Inteligente
            const getCanonicalFamilyId = (i) => {
                if (!i.id_chefe_familia) return i.id;
                // Para evitar ciclos ou vínculos mútuos, pegamos sempre o menor ID (string) entre o membro e seu chefe
                return i.id < i.id_chefe_familia ? i.id : i.id_chefe_familia;
            };
            const recentVisits = agendaData.filter(v => v.status === 'Realizada' && moment(v.data_inicio).isAfter(last30d));
            const recentAttempts = agendaData.filter(v => v.status === 'Não realizada' && moment(v.data_inicio).isAfter(last30d));
            const visitedFamilyIds = new Set();
            recentVisits.forEach(v => {
                const member = data.find(m => m.id == v.irmandade_id);
                if (member) visitedFamilyIds.add(getCanonicalFamilyId(member));
            });
            const famAtendidas = visitedFamilyIds.size;

            // 2. Visitas em Atraso (+60d)
            const ativos = data.filter(i => i.status !== 'Inativo');
            let emAtraso = 0;
            ativos.forEach(i => {
                const visits = agendaData.filter(v => (v.irmandade_id == i.id) && v.status === 'Realizada');
                if (visits.length === 0) {
                    emAtraso++;
                } else {
                    const lastDate = moment(Math.max(...visits.map(v => new Date(v.data_inicio))));
                    if (lastDate.isBefore(last60d)) emAtraso++;
                }
            });

            // 3. Novos Músicos (Ano)
            const novosMusicos = data.filter(i => {
                const isMusico = i.perfil_musico || i.cargo_organista || (i.cargos && (i.cargos.includes('Músico') || i.cargos.includes('Organista')));
                if (!isMusico) return false;
                const dOfi = i.data_oficializacao ? moment(i.data_oficializacao) : null;
                const dIni = i.data_inicio_ensaios ? moment(i.data_inicio_ensaios) : null;
                return (dOfi && dOfi.isAfter(startOfYear)) || (dIni && dIni.isAfter(startOfYear));
            }).length;

            // 4. Cobertura Mocidade (%)
            const mocidade = data.filter(i => i.perfil_mocidade || (i.cargos && i.cargos.includes('Mocidade')));
            const mocTotal = mocidade.length;
            const mocVisitada = mocidade.filter(i => {
                 const visits = agendaData.filter(v => v.irmandade_id == i.id && v.status === 'Realizada' && moment(v.data_inicio).isAfter(last60d));
                 return visits.length > 0;
            }).length;
            const cobMoc = mocTotal > 0 ? Math.round((mocVisitada / mocTotal) * 100) : 0;

            // 5. Total Base
            const totalBase = data.length;

            // 6. Visitas Agendadas (Futuras)
            const visitasAgendadas = agendaData.filter(v => moment(v.data_inicio).isAfter(now) && v.status !== 'Realizada').length;

            // Atualização dos Widgets
            $('#widget-total-fam').text(famAtendidas);
            $('#widget-total-atraso').text(emAtraso);
            $('#widget-total-musicos').text(novosMusicos);
            $('#widget-total-cob-moc').text(cobMoc + '%');
            $('#widget-total-base').text(totalBase);
            $('#widget-total-agenda').text(visitasAgendadas);

            const attemptSummary = recentAttempts.length
                ? ` Também houve <b>${recentAttempts.length}</b> tentativa${recentAttempts.length === 1 ? '' : 's'} de visita sem atendimento nos últimos 30 dias.`
                : '';
            $('#exec-text').html(`<b>Relatório Consolidado:</b> Foram analisados <b>${data.length}</b> membros. Identificado que <b>${famAtendidas}</b> núcleos familiares receberam assistência recente.${attemptSummary}`);
        };

        const updateSelects = (selectedValueOverride) => {
            const $select = $('#irm-chefe-select');
            // Nunca reutilize o valor que ficou no DOM de outro cadastro.
            // O valor só é preservado quando a edição o informa explicitamente.
            const selectedValue = selectedValueOverride === undefined
                ? ''
                : String(selectedValueOverride || '');
            const currentId = String($('#irm-id').val() || '');
            const candidates = irmandadeData.filter(i => String(i.id) !== currentId);
            const useNativeSelect = window.matchMedia('(max-width: 767.98px), (pointer: coarse)').matches;

            if ($select.hasClass('select2-hidden-accessible')) {
                $select.select2('destroy');
            }

            $select.empty().append(new Option('Nenhum (Este membro é o Chefe)', ''));
            candidates.forEach(member => {
                const address = String(member.endereco || '').replace(/^\[[^\]]+\]\s*/, '').trim();
                const detail = member.setor || address;
                const option = new Option(
                    useNativeSelect && detail ? `${member.nome} - ${detail}` : member.nome,
                    member.id
                );
                option.dataset.address = address;
                option.dataset.sector = member.setor || '';
                $select.append(option);
            });
            if (selectedValue && candidates.some(i => String(i.id) === selectedValue)) {
                $select.val(selectedValue);
            } else {
                $select.val('');
            }

            // Em dispositivos touch, o select nativo é mais estável e acessível.
            if (useNativeSelect || !$.fn.select2) {
                $select.removeClass('select2-hidden-accessible').attr('tabindex', '0');
                return;
            }

            $select.select2({
                dropdownParent: $('#modal-cadastro'),
                placeholder: 'Selecione o Chefe da Família...',
                allowClear: true,
                width: '100%',
                templateResult: option => {
                    if (!option.id) return option.text;
                    const element = option.element;
                    const detail = element?.dataset?.sector || element?.dataset?.address || '';
                    const $result = $('<span>');
                    $('<span>', { class: 'family-option-name', text: option.text }).appendTo($result);
                    if (detail) $('<span>', { class: 'family-option-detail', text: detail }).appendTo($result);
                    return $result;
                }
            });
            $select.val(selectedValue || '').trigger('change.select2');
        };

        const getBadgeInfo = (cargo) => {
            const raw = cargo || '';
            const c = raw.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
            const match = (str) => c.includes(str.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""));
            
            if (match('anciao')) return { class: 'badge-anciao', icon: 'fa-user-tie' };
            if (match('diacono')) return { class: 'badge-diacono', icon: 'fa-user-check' };
            if (match('piedade')) return { class: 'badge-piedade', icon: 'fa-hand-holding-heart' };
            if (match('cooperador')) return { class: 'badge-cooperador', icon: 'fa-hands-helping' };
            if (match('encarregado')) return { class: 'badge-encarregado', icon: 'fa-star' };
            if (match('musico')) return { class: 'badge-musico', icon: 'fa-music' };
            if (match('organista')) return { class: 'badge-organista', icon: 'fa-keyboard' };
            if (match('examinadora')) return { class: 'badge-examinadora', icon: 'fa-clipboard-check' };
            if (match('instrutor')) return { class: 'badge-instrutor', icon: 'fa-chalkboard-teacher' };
            if (match('secretar')) return { class: 'badge-secretaria', icon: 'fa-file-signature' };
            if (match('auxiliar de jovens')) return { class: 'badge-auxiliar', icon: 'fa-user-check' };
            if (match('mocidade') || match('jovens')) return { class: 'badge-mocidade', icon: 'fa-child' };
            if (match('enfermo')) return { class: 'badge-enfermo', icon: 'fa-heartbeat' };
            if (match('porteiro')) return { class: 'badge-porteiro', icon: 'fa-door-open' };
            if (match('auxiliar da porta')) return { class: 'badge-auxiliar', icon: 'fa-user-check' };
            if (match('auxiliar de escrita')) return { class: 'badge-escrita', icon: 'fa-pen' };
            if (match('cozinha')) return { class: 'badge-cozinha', icon: 'fa-utensils' };
            if (match('limpeza')) return { class: 'badge-limpeza', icon: 'fa-broom' };
            if (match('estacionamento')) return { class: 'badge-estacionamento', icon: 'fa-car' };
            if (match('ebi')) return { class: 'badge-ebi', icon: 'fa-child' };
            if (match('emi')) return { class: 'badge-emi', icon: 'fa-music' };
            if (match('som')) return { class: 'badge-som', icon: 'fa-volume-up' };
            if (match('manutencao') || match('manutenção')) return { class: 'badge-manutencao', icon: 'fa-tools' };
            if (match('reuniao') || match('reunião')) return { class: 'badge-reuniao', icon: 'fa-home' };
            if (match('grupo de visitas')) return { class: 'badge-grupo-visitas', icon: 'fa-people-group' };
            if (match('irmandade')) return { class: 'badge-irmandade', icon: 'fa-user' };

            return { class: 'badge-servico', icon: 'fa-hands-helping' };
        };

        const renderItems = (items) => {
            const tbody = $('#table-body');
            tbody.empty();
            
            items.forEach(item => {
                // Acompanhamento mais recente: realizada ou tentativa presencial.
                // Cancelada não conta, pois a equipe não chegou a realizar a saída.
                const visits = agendaData.filter(a =>
                    (a.irmandade_id == item.id || a.id_membro == item.id)
                    && (a.status === 'Realizada' || a.status === 'Não realizada')
                );
                let lastVisitHtml = '<span class="text-muted small">Nunca Visitado</span>';
                
                if (visits.length > 0) {
                    const latestVisit = visits.reduce((latest, visit) =>
                        new Date(visit.data_inicio) > new Date(latest.data_inicio) ? visit : latest
                    );
                    const lastDate = moment(latestVisit.data_inicio);
                    const diffDays = moment().diff(lastDate, 'days');
                    if (latestVisit.status === 'Não realizada') {
                        const attemptReason = escapeHtml(latestVisit.motivo_cancelamento || 'A equipe esteve no local, mas a visita não foi realizada.');
                        lastVisitHtml = `
                            <div class="text-center" title="${attemptReason}">
                                <span class="badge bg-warning-100 text-warning border border-warning">Tentativa ${lastDate.fromNow()}</span>
                                <div class="small text-warning mt-1"><i class="fa fa-exclamation-circle me-1"></i>Sem atendimento</div>
                            </div>`;
                    } else {
                        let color = 'success';
                        if (diffDays > 30) color = 'warning';
                        if (diffDays > 60) color = 'danger';
                        lastVisitHtml = `<span class="badge bg-${color}-100 text-${color} border border-${color}">${lastDate.fromNow()}</span>`;
                    }
                }

                // Próxima visita somente quando houver agenda vinculada à própria pessoa.
                // Moradores no mesmo endereço não herdam o evento uns dos outros: isso
                // criava uma data aparente no cadastro sem registro correspondente no calendário.
                const finalStatuses = new Set(['Realizada', 'Cancelada', 'Não realizada']);
                const futureVisits = agendaData.filter(a =>
                    !finalStatuses.has(a.status)
                    && moment(a.data_inicio).isSameOrAfter(moment().startOf('day'))
                    && (a.irmandade_id == item.id || a.id_membro == item.id)
                );
                let nextVisitHtml = '<span class="text-muted small">-</span>';

                if (futureVisits.length > 0) {
                    const nextDate = moment(Math.min(...futureVisits.map(v => new Date(v.data_inicio))));
                    nextVisitHtml = `<span class="badge bg-indigo-100 text-indigo border border-indigo" title="Visita agendada"><i class="fa fa-calendar-alt me-1"></i>${nextDate.format('DD/MM/YY')}</span>`;
                }

                // Renderização de Cargos (Agregação de Fontes)
                let cargosArr = (item.cargo_outros || '').split(',').map(c => c.trim()).filter(c => c !== '');
                
                if (item.perfil_musico) cargosArr.push('Músico');
                if (item.cargo_organista) cargosArr.push('Organista');
                if (item.perfil_mocidade) cargosArr.push('Mocidade');
                if (item.perfil_enfermo) cargosArr.push('Enfermo');
                if (item.cargo_porteiro) cargosArr.push('Porteiro');
                if (item.cargo_auxiliar_porta) cargosArr.push('Auxiliar da Porta');
                
                // Remover duplicatas e vazio
                cargosArr = [...new Set(cargosArr)].filter(c => c);

                const badgesHtml = cargosArr.map(c => {
                    const info = getBadgeInfo(c);
                    return `<span class="badge-ministerio ${info.class}"><i class="fa ${info.icon}"></i> ${c}</span>`;
                }).join('');
                const equipeBadgeHtml = item.equipe_visita
                    ? `<span class="badge-ministerio badge-equipe-visita" title="Equipe do Grupo de Visitas"><i class="fa fa-route"></i> ${item.equipe_visita}</span>`
                    : '';
                const periodoVisitaHtml = item.preferencia_periodo_visita
                    ? `<span class="badge ${item.preferencia_periodo_visita === 'Manhã' ? 'bg-warning-100 text-warning' : 'bg-indigo-100 text-indigo'} border" title="Preferência de período da visita"><i class="fa ${item.preferencia_periodo_visita === 'Manhã' ? 'fa-sun' : 'fa-cloud-sun'} me-1"></i>Prefere ${item.preferencia_periodo_visita.toLowerCase()}</span>`
                    : '';
                const classificacaoAdicionalHtml = item.classificacao_adicional
                    ? `<span class="badge bg-teal-100 text-teal border" title="Classificação adicional; não altera a categoria regional"><i class="fa fa-tag me-1"></i>${item.classificacao_adicional}</span>`
                    : '';
                const apontamentosRestritosHtml = CAN_VIEW_RESTRICTED_NOTES && item.apontamentos_restritos
                    ? `<div class="alert alert-danger border-danger py-2 px-3 mt-2 mb-0 small" role="note"><i class="fa fa-user-shield me-1"></i><strong>Apontamento restrito:</strong> ${$('<div>').text(item.apontamentos_restritos).html()}</div>`
                    : '';
                const preferenciasHtml = periodoVisitaHtml || classificacaoAdicionalHtml
                    ? `<div class="d-flex flex-wrap align-items-center gap-2 mt-1">${periodoVisitaHtml}${classificacaoAdicionalHtml}</div>`
                    : '';

                const photoHtml = item.url_foto 
                    ? `<img src="${item.url_foto}" class="rounded-circle shadow-sm" style="width: 40px; height: 40px; object-fit: cover;">`
                    : `<div class="bg-light rounded-circle d-flex align-items-center justify-content-center text-primary fw-bold" style="width: 40px; height: 40px;">${item.nome.charAt(0)}</div>`;
                const addressDisplay = String(item.endereco || '').replace(/^\[[^\]]+\]\s*/, '').trim();

                tbody.append(`
                    <tr>
                        <td class="ps-3 py-3">
                            <div class="d-flex align-items-center">
                                <div class="symbol symbol-40px me-3">
                                    ${photoHtml}
                                </div>
                                <div>
                                    <a href="javascript:;" onclick="handleAction('${item.id}', 'edit')" class="fw-bold text-dark text-decoration-none d-block fs-14px">${item.nome}</a>
                                    ${addressDisplay ? `<small class="text-muted d-block text-truncate" style="max-width: 360px;" title="${escapeHtml(addressDisplay)}"><i class="fa fa-home text-secondary me-1"></i>${escapeHtml(addressDisplay)}</small>` : ''}
                                    <small class="text-muted d-flex align-items-center gap-1">
                                        <i class="fa fa-map-marker-alt text-danger"></i> ${item.comum || 'Comum não informada'}
                                    </small>
                                    ${item.id_chefe_familia ? (() => {
                                        const chefe = irmandadeData.find(i => i.id == item.id_chefe_familia);
                                        return `<div class="mt-1"><span class="badge bg-blue-100 text-blue-700 border border-blue-200" style="font-size: 9px;"><i class="fa fa-users me-1"></i> ${item.vinculo_tipo || 'Familiar'} de ${chefe ? chefe.nome : 'Chefe'}</span></div>`;
                                    })() : ''}
                                    ${preferenciasHtml}
                                    ${apontamentosRestritosHtml}
                                </div>
                            </div>
                        </td>
                        <td><div class="d-flex flex-wrap gap-1">${badgesHtml || '<span class="badge-ministerio badge-irmandade"><i class="fa fa-user"></i> Irmandade</span>'}${equipeBadgeHtml}</div></td>
                        <td class="text-center">${lastVisitHtml}</td>
                        <td class="text-center">${nextVisitHtml}</td>
                        <td class="text-center">
                            <span class="badge border border-${item.status === 'Inativo' ? 'danger text-danger' : 'success text-success'} px-2 py-1 rounded-pill">
                                ${item.status || 'Ativo'}
                            </span>
                        </td>
                        <td class="text-center">
                            <div class="btn-group">
                                <button class="btn btn-white btn-sm border" title="Histórico de Visitação" onclick="viewHistory('${item.id}')"><i class="fa fa-history text-info"></i></button>
                                <button class="btn btn-white btn-sm border" title="Editar" onclick="handleAction('${item.id}', 'edit')"><i class="fa fa-edit text-blue"></i></button>
                                <button class="btn btn-white btn-sm border" title="Excluir" onclick="deleteItem('${item.id}')"><i class="fa fa-trash text-danger"></i></button>
                            </div>
                        </td>
                    </tr>
                `);
            });
            $('#record-count').text(`Sincronização completa: ${items.length} registros ministeriais`);
        };

        const openModalCadastro = () => {
            $('#form-cadastro')[0].reset();
            $('#irm-id').val('');
            $('#irm-comum').val(cadastroSelectedCommon || CADASTRO_DEFAULT_COMMON);
            $('#irm-cidade').val(cadastroSelectedCity || CADASTRO_DEFAULT_CITY);
            $('#irm-url-foto').val('');
            $('#photo-preview').html('<i class="fa fa-user-circle fa-7x text-muted opacity-2"></i>');
            updateSelects('');
            $('#irm-chefe-select').val('').trigger('change');
            $('input[name="cargo"]').prop('checked', false);
            $('#modal-cadastro').modal('show');
        };

        const lookupCEP = async () => {
            const cep = $('#irm-cep').val().replace(/\D/g, '');
            if (cep.length !== 8) return;

            try {
                const res = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
                const data = await res.json();
                
                if (data.erro) {
                    AppFeedback.show({
                        type: 'warning',
                        title: 'CEP não encontrado',
                        message: 'Confira o número informado e tente novamente.'
                    });
                    return;
                }

                $('#irm-endereco').val(`${data.logradouro}, ${data.localidade} - ${data.uf}`);
                $('#irm-setor').val(data.bairro);
                $('#irm-cidade').val(data.localidade);
                
                // Disparar Geocodificação Automática com endereço completo para melhor precisão
                const fullAddress = `${data.logradouro}, ${data.bairro}, ${data.localidade}, ${data.uf}, Brasil`;
                geocodeAddress(fullAddress);
                
            } catch (err) {
                console.error("Erro no ViaCEP:", err);
            }
        };

        const geocodeAddress = async (address) => {
            try {
                const res = await fetch(`/visitas/api/geocode/?address=${encodeURIComponent(address)}`);
                const data = await res.json();
                
                if (data.lat && data.lng) {
                    $('#irm-gps').val(`${data.lat}, ${data.lng}`);
                    // Feedback visual sutil
                    $('#irm-gps').addClass('is-valid');
                    setTimeout(() => $('#irm-gps').removeClass('is-valid'), 2000);
                }
            } catch (err) {
                console.error("Erro na geocodificação:", err);
            }
        };

        const previewPhoto = (input) => {
            if (input.files && input.files[0]) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    $('#photo-preview').html(`<img src="${e.target.result}" style="width: 100%; height: 100%; object-fit: cover;">`);
                };
                reader.readAsDataURL(input.files[0]);
            }
        };

        // UX: Drag & Drop e Paste
        $(document).ready(() => {
            // Auto-preenchimento de endereço ao selecionar Chefe
            $('#irm-chefe-select').on('change', function() {
                const chefeId = $(this).val();
                if (chefeId && !$('#irm-endereco').val()) {
                    const chefe = irmandadeData.find(i => i.id == chefeId);
                    if (chefe) {
                        Swal.fire({
                            title: 'Mesmo endereço?',
                            text: `Deseja copiar o endereço de ${chefe.nome}?`,
                            icon: 'question',
                            showCancelButton: true,
                            confirmButtonText: 'Sim, copiar',
                            cancelButtonText: 'Não, preencher manual'
                        }).then((result) => {
                            if (result.isConfirmed) {
                                $('#irm-cep').val(chefe.cep || '');
                                $('#irm-setor').val(chefe.setor || '');
                                $('#irm-complemento').val(chefe.complemento || '');
                                
                                // Extrair endereço sem o GPS [lat,lng]
                                const fullAddr = chefe.endereco || '';
                                const cleanAddr = fullAddr.includes('] ') ? fullAddr.split('] ')[1] : fullAddr;
                                const gpsMatch = fullAddr.match(/^\[([-.\d]+),\s*([-.\d]+)\]/);
                                
                                $('#irm-endereco').val(cleanAddr);
                                if (gpsMatch) $('#irm-gps').val(`${gpsMatch[1]}, ${gpsMatch[2]}`);
                                
                                toastr.success('Endereço copiado com sucesso!');
                            }
                        });
                    }
                }
            });

            // Máscara para CEP
            $('#irm-cep').on('input', function() {
                let v = $(this).val().replace(/\D/g, '');
                if (v.length > 5) v = v.substring(0, 5) + '-' + v.substring(5, 8);
                $(this).val(v);
                if (v.length === 9) lookupCEP();
            });

            // Máscara brasileira para celular/telefone com DDD.
            $('#irm-celular').on('input', function() {
                const digits = $(this).val().replace(/\D/g, '').substring(0, 11);
                let formatted = digits;
                if (digits.length > 2) formatted = `(${digits.substring(0, 2)}) ${digits.substring(2, 3)}`;
                if (digits.length > 3) formatted += ` ${digits.substring(3, 7)}`;
                if (digits.length > 7) formatted += `-${digits.substring(7, 11)}`;
                $(this).val(formatted);
            });

            const dropZone = document.getElementById('photo-preview');
            
            if (dropZone) {
                ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                    dropZone.addEventListener(eventName, e => { e.preventDefault(); e.stopPropagation(); }, false);
                });

                ['dragenter', 'dragover'].forEach(eventName => {
                    dropZone.addEventListener(eventName, () => dropZone.style.borderColor = '#348fe2', false);
                });

                ['dragleave', 'drop'].forEach(eventName => {
                    dropZone.addEventListener(eventName, () => dropZone.style.borderColor = '#fff', false);
                });

                dropZone.addEventListener('drop', e => {
                    const dt = e.dataTransfer;
                    const files = dt.files;
                    if (files.length) {
                        const input = document.getElementById('irm-foto-input');
                        input.files = files;
                        previewPhoto(input);
                    }
                }, false);
            }

            // Suporte para colar imagem (CTRL+V)
            window.addEventListener('paste', e => {
                if (!$('#modal-cadastro').hasClass('show')) return;
                
                const items = e.clipboardData.items;
                for (let i = 0; i < items.length; i++) {
                    if (items[i].type.indexOf('image') !== -1) {
                        const blob = items[i].getAsFile();
                        const file = new File([blob], `pasted_img_${Date.now()}.png`, { type: blob.type });
                        
                        const dt = new DataTransfer();
                        dt.items.add(file);
                        const input = document.getElementById('irm-foto-input');
                        input.files = dt.files;
                        previewPhoto(input);
                        break;
                    }
                }
            });
        });

        const handleAction = async (id, type) => {
            const item = irmandadeData.find(i => i.id == id);
            if (!item) return;

            $('#form-cadastro')[0].reset();
            $('#irm-id').val(item.id);
            $('#irm-nome').val(item.nome);
            $('#irm-cep').val(item.cep || '');
            $('#irm-comum').val(item.comum || '');
            $('#irm-cidade').val(item.cidade || '');
            const addressRaw = item.endereco || '';
            const coordMatch = addressRaw.match(/^\[([-.\d]+),\s*([-.\d]+)\]\s*(.*)/);
            
            if (coordMatch) {
                $('#irm-gps').val(`${coordMatch[1]}, ${coordMatch[2]}`);
                $('#irm-endereco').val(coordMatch[3]);
            } else {
                $('#irm-gps').val('');
                $('#irm-endereco').val(addressRaw);
            }

            $('#irm-status').val(item.status || 'Ativo');
            $('#irm-setor').val(item.setor || '');
			$('#irm-preferencia-periodo-visita').val(item.preferencia_periodo_visita || '');
			$('#irm-classificacao-adicional').val(item.classificacao_adicional || '');
			if (CAN_VIEW_RESTRICTED_NOTES) $('#irm-apontamentos-restritos').val(item.apontamentos_restritos || '');
            $('#irm-celular').val(item.celular || '').trigger('input');
            $('#irm-complemento').val(item.complemento || '');
            // O select é reconstruído quando o modal abre. Recrie as opções
            // antes de aplicar o valor para que o vínculo não seja descartado
            // quando o cadastro é editado pela primeira vez.
            updateSelects(item.id_chefe_familia || '');
			$('#irm-chefe-select').val(item.id_chefe_familia || '').trigger('change');
            $('#irm-vinculo-tipo').val(item.vinculo_tipo || '');
            
            // Foto
            $('#irm-url-foto').val(item.url_foto || '');
            if (item.url_foto) {
                $('#photo-preview').html(`<img src="${item.url_foto}" style="width: 100%; height: 100%; object-fit: cover;">`);
            } else {
                $('#photo-preview').html('<i class="fa fa-user-circle fa-7x text-muted opacity-2"></i>');
            }

            // Datas
            $('#irm-nascimento').val(item.data_nascimento);
            $('#irm-batismo').val(item.data_batismo);
            $('#irm-ensaios').val(item.data_inicio_ensaios);
            $('#irm-oficial').val(item.data_culto_oficial);
            $('#irm-graduacao').val(item.data_oficializacao);

            // Cargos Checkboxes
            const cargosArr = (item.cargo_outros || '').split(',').map(c => c.trim());
            $('input[name="cargo"]').prop('checked', false);
            
            // Check based on profile flags first
            if (item.perfil_musico) $(`input[name="cargo"][value="Músico"]`).prop('checked', true);
            if (item.cargo_organista) $(`input[name="cargo"][value="Organista"]`).prop('checked', true);
            if (item.perfil_enfermo) $(`input[name="cargo"][value="Enfermo"]`).prop('checked', true);
            if (item.cargo_porteiro) $(`input[name="cargo"][value="Porteiro"]`).prop('checked', true);
            if (item.cargo_auxiliar_porta) $(`input[name="cargo"][value="Auxiliar da Porta"]`).prop('checked', true);
            
            // Check based on "outros" string
            cargosArr.forEach(c => {
                if(c) $(`input[name="cargo"][value="${c}"]`).prop('checked', true);
            });
            
            const isView = type === 'view';
            $('#btn-save-cadastro').toggle(!isView);
            $('#form-cadastro input, #form-cadastro select').prop('disabled', isView);
            $('#modal-cadastro').modal('show');
        };

        const saveCadastro = async () => {
            const id = $('#irm-id').val();
            
            let seleccionados = [];
            $('input[name="cargo"]:checked').each(function() { seleccionados.push($(this).val()); });
            const extra = $('#cargo-extra').val();
            if (extra) seleccionados.push(extra);

            let outros = [];
            // Cargos sem coluna própria permanecem em cargo_outros para conservar
            // sua identidade ministerial (ex.: Cooperador/Auxiliar de Jovens).
            const mappedValues = ['Músico', 'Organista', 'Enfermo', 'Porteiro', 'Auxiliar da Porta'];
            seleccionados.forEach(c => {
                if (!mappedValues.includes(c)) outros.push(c);
            });

            // LÓGICA DE UPLOAD DE FOTO (PROXY)
            let urlFoto = $('#irm-url-foto').val();
            const photoFile = $('#irm-foto-input')[0].files[0];
            const currentRecord = irmandadeData.find(item => String(item.id) === String(id));
            
            if (photoFile) {
                const formData = new FormData();
                formData.append('file', photoFile);
                formData.append('name', $('#irm-nome').val() || 'perfil');
                
                try {
                    const uploadRes = await fetch('/visitas/api/upload/', {
                        method: 'POST',
                        headers: { 'X-CSRFToken': 'null' },
                        body: formData
                    });
                    
                    const uploadData = await uploadRes.json();
                    
                    if (!uploadRes.ok) {
                        throw new Error(uploadData.details || "Erro desconhecido no servidor de fotos.");
                    }

                    if (uploadData.url) {
                        urlFoto = uploadData.url;
                    }
                } catch (err) {
                    console.error("Erro no upload da foto:", err);
                    AppFeedback.show({
                        type: 'error',
                        flow: 'upload',
                        title: 'Falha no upload da foto',
                        message: `Não foi possível salvar a imagem: ${err.message}`,
                        detail: 'Revise o arquivo e tente novamente. Se o problema continuar, contate o administrador.'
                    });
                    return; // Bloqueia o salvamento do registro
                }
            }

            const payload = {
                nome: $('#irm-nome').val(),
                cep: $('#irm-cep').val(),
                comum: $('#irm-comum').val(),
                cidade: $('#irm-cidade').val().trim(),
                id_chefe_familia: $('#irm-chefe-select').val() || null,
                vinculo_tipo: $('#irm-vinculo-tipo').val(),
                setor: $('#irm-setor').val(),
                preferencia_periodo_visita: $('#irm-preferencia-periodo-visita').val() || null,
                classificacao_adicional: $('#irm-classificacao-adicional').val().trim() || null,
                ...(CAN_VIEW_RESTRICTED_NOTES ? {apontamentos_restritos: $('#irm-apontamentos-restritos').val().trim() || null} : {}),
                celular: $('#irm-celular').val().trim() || null,
                complemento: $('#irm-complemento').val().trim() || null,
                endereco: ($('#irm-gps').val() ? `[${$('#irm-gps').val()}] ` : '') + $('#irm-endereco').val(),
                status: $('#irm-status').val(),
                url_foto: urlFoto,
                updated_at: new Date().toISOString(),
                data_nascimento: $('#irm-nascimento').val() || null,
                data_batismo: $('#irm-batismo').val() || null,
                data_inicio_ensaios: $('#irm-ensaios').val() || null,
                data_culto_oficial: $('#irm-oficial').val() || null,
                data_oficializacao: $('#irm-graduacao').val() || null,
				perfil_musico: seleccionados.includes('Músico'),
				cargo_organista: seleccionados.includes('Organista'),
				perfil_mocidade: seleccionados.includes('Auxiliar de Jovens') || seleccionados.includes('Cooperador de Jovens') ? false : Boolean(currentRecord?.perfil_mocidade),
                perfil_enfermo: seleccionados.includes('Enfermo'),
                cargo_porteiro: seleccionados.includes('Porteiro'),
                cargo_auxiliar_porta: seleccionados.includes('Auxiliar da Porta'),
                cargo_outros: outros.join(',')
            };

            const url = id ? `/visitas/api/irmandade/?id=${id}` : '/visitas/api/irmandade/';
            const nomeCadastro = String(payload.nome || '').trim() || 'este membro';
            const saveFlow = id ? 'update' : 'create';
            const saveNotice = AppFeedback.show({
                type: 'loading',
                flow: saveFlow,
                title: id ? 'Atualizando cadastro' : 'Realizando cadastro',
                message: `Aguarde enquanto salvamos os dados de ${nomeCadastro}.`
            });
            try {
                const requestOptions = {
                    method: id ? 'PATCH' : 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': 'null' },
                    body: JSON.stringify(payload)
                };
                let res;
                try {
                    res = await fetch(url, requestOptions);
                } catch (firstError) {
                    // Tolera uma reinicialização rápida do servidor de desenvolvimento.
                    await new Promise(resolve => setTimeout(resolve, 900));
                    res = await fetch(url, requestOptions);
                }

                if (res.ok) {
                    saveNotice.close();
                    $('#modal-cadastro').modal('hide');
                    await loadContent();
                    AppFeedback.show({
                        type: 'success',
                        flow: saveFlow,
                        title: id ? 'Cadastro atualizado' : 'Cadastro realizado',
                        message: `${nomeCadastro} foi salvo com sucesso.`,
                        detail: 'Os dados foram salvos e a lista de irmandade foi atualizada.'
                    });
                } else {
                    const errData = await res.json();
                    let msg = "Desculpe, ocorreu um erro ao salvar os dados.";
                    
                    // Tradução amigável de erros do Supabase/PostgREST
                    if (errData.details) {
                        const details = typeof errData.details === 'string' ? errData.details : JSON.stringify(errData.details);
                        if (details.includes('PGRST204')) msg = "Erro de configuração: Um campo enviado não existe no servidor. Por favor, contate o suporte.";
                        else if (details.includes('23505')) msg = "Este registro já existe (duplicidade detectada).";
                        else if (details.includes('PGRST')) msg = "Erro de banco de dados. Verifique os campos e tente novamente.";
                    }
                    
                    console.error("Erro Original:", errData);
                    saveNotice.close();
                    AppFeedback.show({
                        type: 'error',
                        flow: saveFlow,
                        title: 'Não foi possível salvar',
                        message: msg
                    });
                }
            } catch (e) {
                console.error('Falha de conexão ao salvar cadastro:', e);
                saveNotice.close();
                AppFeedback.show({
                    type: 'error',
                    flow: saveFlow,
                    title: 'Servidor indisponível',
                    message: 'O servidor não respondeu. Aguarde alguns segundos e tente novamente.'
                });
            }
        };

        const handleSearch = async (val) => {
            const rawValue = String(val || '').trim();
            // A busca só amplia o escopo quando não há uma comum específica
            // selecionada (município inteiro ou Regional inteira). Com uma
            // comum escolhida, o texto permanece restrito a ela.
            const canSearchAcrossCommons = CADASTRO_ACCESS_LEVEL !== 'local' && !cadastroSelectedCommon;
            if (rawValue && canSearchAcrossCommons && !searchAcrossCommons) {
                // A pesquisa deve abranger todas as comuns visíveis ao usuário,
                // mesmo quando o filtro territorial está apontado para uma comum.
                searchAcrossCommons = true;
                await loadContent({ allCommons: true });
                return;
            }
            if (!rawValue && searchAcrossCommons) {
                searchAcrossCommons = false;
                await loadContent();
                return;
            }
            const normalizeSearch = value => String(value || '')
                .normalize('NFD')
                .replace(/[\u0300-\u036f]/g, '')
                .toLowerCase()
                .trim();
            const terms = rawValue
                .split(',')
                .map(normalizeSearch)
                .filter(Boolean);
            const filtered = !terms.length ? irmandadeData : irmandadeData.filter(item => {
                const familyHead = item.id_chefe_familia
                    ? irmandadeData.find(member => member.id == item.id_chefe_familia)?.nome
                    : '';
                const searchableText = normalizeSearch([
                    item.nome,
                    item.comum,
                    item.familia,
                    familyHead
                ].filter(Boolean).join(' '));
                const searchableWords = searchableText.split(/\s+/).filter(Boolean);
                return terms.some(term => {
                    const requestedWords = term.split(/\s+/).filter(Boolean);
                    return requestedWords.every(requestedWord =>
                        searchableWords.some(word => word.startsWith(requestedWord))
                    );
                });
            });
            renderItems(filtered);
        };

        window.deleteItem = async (id) => {
            const member=irmandadeData.find(item=>String(item.id)===String(id)),fullName=String(member?.nome||'este registro').trim(),firstName=fullName.split(/\s+/)[0]||'O registro';
            const confirmed=await AppFeedback.confirm({title:`Excluir ${fullName}?`,message:'O cadastro será removido permanentemente e esta ação não poderá ser desfeita.',confirmText:'Sim, excluir'});if(!confirmed)return;
            const notice=AppFeedback.show({type:'loading',flow:'delete',title:'Excluindo cadastro',message:'Aguarde, o registro está sendo removido.'});
            try{const response=await fetch(`/visitas/api/irmandade/?id=${encodeURIComponent(id)}`,{method:'DELETE',headers:{'X-CSRFToken':'null'}}),result=await response.json().catch(()=>({}));if(!response.ok)throw new Error(result.error||result.details||'Não foi possível excluir o cadastro.');notice.close();await loadContent();AppFeedback.show({type:'success',title:'Cadastro excluído',message:`O cadastro de ${firstName} foi excluído com sucesso.`})}catch(error){notice.close();AppFeedback.show({type:'error',title:'Não foi possível excluir',message:error.message})}
        };

        const CATEGORY_MAP = {
            'GVI': { label: 'GVI: Irmandade', bg: 'bg-gvi', text: 'text-gvi', icon: 'fa-users' },
            'GVM': { label: 'GVM: Mocidade', bg: 'bg-gvm', text: 'text-gvm', icon: 'fa-child' },
            'GVE': { label: 'GVE: Encarregados', bg: 'bg-gve', text: 'text-gve', icon: 'fa-music' },
            'RF': { label: 'RF: Reunião Familiar', bg: 'bg-rf', text: 'text-rf', icon: 'fa-home' },
            'RE': { label: 'RE: Reunião de Evangelização', bg: 'bg-re', text: 'text-re', icon: 'fa-bullhorn' }
        };

        window.viewHistory = async (id) => {
            const member = irmandadeData.find(m => m.id == id);
            if (!member) return;

            $('#hist-nome').text(member.nome);
            
            const modalEl = document.getElementById('modal-historico');
            if (modalEl) {
                const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                modal.show();
            }

            try {
                let history = agendaData.filter(v => v.irmandade_id == id || v.id_membro == id);
                
                if (history.length === 0) {
                    $('#timeline-container').html('<div class="alert alert-light text-center py-5 border-dashed"><i class="fa fa-folder-open fa-3x text-gray-300 mb-3 d-block"></i>Nenhuma visita registrada para este membro.</div>');
                    return;
                }

                const getHistoryStyle = (categoria, equipe) => {
                    const cfg = CATEGORY_MAP[categoria] || CATEGORY_MAP['GVI'];
                    return { icon: cfg.icon, bg: cfg.bg, label: cfg.label, text: cfg.text, eq: equipe || 'Equipe Ministerial' };
                };

                let html = '<div class="timeline-v2">';
                history.sort((a,b) => new Date(b.data_inicio) - new Date(a.data_inicio)).forEach(v => {
                    const data = moment(v.data_inicio).format('DD/MM/YY');
                    const hora = moment(v.data_inicio).format('HH:mm');
                    const style = getHistoryStyle(v.categoria, v.equipe_responsavel);
                    
                    const diffDays = moment().diff(moment(v.data_inicio), 'days');
                    let timeColor = 'success';
                    if (diffDays > 30) timeColor = 'warning';
                    if (diffDays > 60) timeColor = 'danger';
                    if (diffDays < 0) timeColor = 'indigo';
                    
                    let displayStatus = v.status || 'Marcada';
                    let isPast = moment(v.data_inicio).isBefore(moment());
                    if ((displayStatus === 'Marcada' || displayStatus === 'Agendada') && isPast) {
                        displayStatus = 'Não realizada';
                    }

                    let statusLabel = 'Agendada';
                    let statusIcon = 'fa-clock';
                    let statusColor = 'text-info';

                    if (displayStatus === 'Realizada') {
                        statusLabel = 'Concluída';
                        statusIcon = 'fa-check-circle';
                        statusColor = 'text-success';
                    } else if (displayStatus === 'Não realizada') {
                        statusLabel = 'Não Realizada';
                        statusIcon = 'fa-exclamation-circle';
                        statusColor = 'text-warning';
                    } else if (displayStatus === 'Cancelada') {
                        statusLabel = 'Cancelada';
                        statusIcon = 'fa-times-circle';
                        statusColor = 'text-danger';
                    }

                    let obsText = v.observacoes || (displayStatus === 'Marcada' || displayStatus === 'Agendada' ? 'Aguardando data.' : (displayStatus === 'Realizada' ? 'Visita concluída com sucesso.' : 'Sem observações.'));

                    html += `
                        <div class="timeline-item-v2">
                            <div class="timeline-time-v2">
                                <span class="date">${data}</span>
                                <span class="time">${hora}</span>
                                <span class="mt-2 badge bg-${timeColor}-100 text-${timeColor} border border-${timeColor}" style="font-size: 8px; display: inline-block;">${moment(v.data_inicio).fromNow()}</span>
                            </div>
                            <div class="timeline-icon-v2 ${style.bg}">
                                <i class="fa ${style.icon}"></i>
                            </div>
                            <div class="timeline-content-v2">
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <div class="fw-bold text-dark fs-13px">Visita Ministerial</div>
                                    <small class="${statusColor} fw-bold" style="font-size: 10px;" ${statusColor === 'text-warning' ? 'style="color: #fd7e14 !important;"' : ''}><i class="fa ${statusIcon} me-1"></i> ${statusLabel}</small>
                                </div>
                                <div class="badge-premium ${style.bg} mb-2">
                                    <i class="fa ${style.icon} me-1"></i> ${style.label}
                                </div>
                                <div class="small text-muted mb-2 fst-italic">"${obsText}"</div>
                                <div class="mt-2 pt-2 border-top border-light d-flex align-items-center">
                                    <i class="fa fa-users-cog me-2 text-muted" style="font-size: 10px;"></i>
                                    <small class="fw-bold text-uppercase text-muted" style="font-size: 9px;">Efetuada Por: ${style.eq}</small>
                                </div>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                $('#timeline-container').html(html);
            } catch (err) {
                $('#timeline-container').html('<div class="alert alert-danger">Erro técnico ao carregar histórico. Tente novamente.</div>');
            }
        };

        const fillCadastroCommonSelect = () => {
            const select = document.getElementById('cadastro-common-filter');
            if (!select) return;
            const available = CADASTRO_COMMONS.filter(item => !cadastroSelectedCity || item.cidade === cadastroSelectedCity);
            select.replaceChildren(new Option('Selecione a comum...', ''));
            available.forEach(item => select.add(new Option(item.comum, item.comum)));
            if (available.some(item => item.comum === cadastroSelectedCommon)) select.value = cadastroSelectedCommon;
            const $select = jQuery(select);
            if ($select.hasClass('select2-hidden-accessible')) $select.select2('destroy');
            $select.select2({
                width: '100%', language: 'pt-BR', allowClear: true,
                placeholder: 'Digite o código ou nome da comum...'
            });
        };

        const configureCadastroScope = () => {
            const citySelect = document.getElementById('cadastro-municipio-filter');
            const commonSelect = document.getElementById('cadastro-common-filter');
            if (citySelect) {
                citySelect.value = cadastroSelectedCity;
                citySelect.addEventListener('change', async () => {
                    cadastroSelectedCity = citySelect.value;
                    cadastroSelectedCommon = '';
                    searchAcrossCommons = false;
                    $('#irmandade-search').val('');
                    fillCadastroCommonSelect();
                    await loadContent();
                });
            }
            fillCadastroCommonSelect();
            if (commonSelect) {
                jQuery(commonSelect).off('change.cadastroScope').on('change.cadastroScope', async () => {
                    cadastroSelectedCommon = commonSelect.value || '';
                    searchAcrossCommons = false;
                    $('#irmandade-search').val('');
                    await loadContent();
                });
            }
        };

        $(document).ready(() => {
            configureCadastroScope();
            loadContent();
        });
    