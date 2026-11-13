# Importação de resultados de exames

Em **Música > Exames > Resultados dos exames**, use **Importar resultados**. O envio apenas prepara a prévia; a gravação ocorre em **Importar N selecionadas**.

A conferência usa uma lista compacta com nome, comum, etapa, resultado e situação. Data e evento ficam no topo e são aplicados ao lote. **Mais opções do lote** reúne o resultado padrão para linhas sem resultado e a reaplicação das configurações. **Ajustar** abre os campos individuais de uma única aluna. Busca, **Só pendências** e **Selecionar visíveis** ajudam a revisar apenas as exceções; filtrar a lista não altera a seleção das linhas ocultas. O botão **Importar N selecionadas** mostra a quantidade total que será enviada.

São aceitos XLSX, PDF, CSV, TSV, TXT e imagens JPG, PNG, WebP, TIFF e BMP, com até 12 MB. PDF é limitado a 30 páginas e o lote a 500 resultados. XLSX pode conter abas RJM, Culto Oficial e Oficialização; havendo abas por etapa, a aba geral não é importada novamente. Tabelas comuns usam Nome, Comum, Tipo, Data e Resultado. Fotografias e PDFs digitalizados passam por OCR e precisam de conferência de nomes, códigos, modalidades e quantidade de linhas.

A comum é identificada pelo código BR do documento e comparada ao cadastro do aluno. O município vem desse cadastro ou do catálogo institucional de comuns, nunca de palavras no nome do bairro. A consulta busca somente as comuns do documento. Cada linha recebe no máximo oito candidatas; o navegador não replica o cadastro regional inteiro em cada seletor.

A identificação ignora acentos, símbolos e partículas da/de/do/das/dos/e. Aceita similaridade mínima de 75%, mantendo a mesma comum e o primeiro nome. Candidatas próximas entre si exigem escolha explícita. Sobrenomes iguais com primeiros nomes diferentes não bastam para identificar a pessoa. A conferência mostra o nome cadastrado e a similaridade; a opção **Atualizar nome do cadastro conforme o documento** mantém o ID, o histórico e os demais dados do aluno. As alterações preservam o ID do aluno e a auditoria existente; não são inseridas informações técnicas nas observações do exame.

Sem candidata compatível, a prévia oferece **Cadastrar**. O servidor reconsulta as candidatas antes de criar, valida a comum e o escopo e exige categoria/instrumento. A criação usa uma identidade estável para permitir repetição sem recriar o mesmo aluno. Os dados pessoais ausentes permanecem para complemento e não se presume consentimento. Todas as linhas são validadas antes de iniciar as gravações. O cadastro só é criado na confirmação, nunca durante a leitura.

O servidor confere novamente o escopo e o código da comum ao confirmar. A leitura tem limite de 90 segundos no navegador, libera o botão e exibe erro se o limite for excedido; a prévia não grava registros. A confirmação envia todas as linhas selecionadas em uma requisição. O servidor valida o lote inteiro antes de gravar, reúne os exames em um único upsert e atualiza seus lançamentos compartilhados em outro. Promoções iguais são agrupadas, sem retroceder níveis ou sobrescrever uma promoção concorrente. O cache dos cadastros é atualizado uma vez ao final, evitando reprocessar a relação regional a cada linha. Cadastros novos e correções diferentes de nome continuam sendo tratados individualmente quando necessário.

Atribua uma data ao lote ou a cada linha. O vínculo com a agenda exige data, categoria e polo municipal compatíveis. Cotia, Caucaia e Vargem Grande Paulista usam o polo de Cotia; Santana e Pirapora usam o polo de Santana/Fazendinha. Eventos ambíguos exigem seleção. Datas históricas sem evento precisam ser identificadas expressamente como registro sem agenda.

Resultado vazio significa **Agendado**, sem promoção automática. É possível aplicar um resultado às linhas pendentes após conferência. Aprovações alimentam a coluna correspondente no quadro, o lançamento compartilhado e o nível do aluno. Cada exame mantém sua própria data no banco e aparece no Progresso do GEM. Aprovar uma etapa anterior não reduz um nível já alcançado.

Reimportações preservam resultados já registrados. Exames agendados podem receber seu resultado na confirmação. Resultados concluídos divergentes devem ser corrigidos pelo histórico individual. Falhas de sincronização são indicadas por linha; repetir a confirmação permite concluir a sincronização sem recriar o exame. Como as integrações existentes usam chamadas REST separadas, pode haver gravação parcial em falhas de rede.

Em **Resumo do aluno > Editar**, os campos de aprovações históricas permitem registrar separadamente RJM, Culto Oficial e Oficialização. São registros de aprovação efetiva, não previsão de exame. Datas existentes aparecem no resumo; correções devem ser feitas no histórico de exames.

O menu **Exportar resultados > Excel / PDF** respeitam os filtros gerais e a pesquisa/filtros da tabela individual, seguindo `REPORT_EXPORT_STANDARD.md`.

## Execução

As tabelas e a auditoria são as existentes na migração `022_musica_exames_individuais.sql`; este fluxo não exige tabela adicional. Instale as dependências de `requirements.txt`. No Windows, o OCR usa o recurso nativo do sistema e seus idiomas instalados. Em outros sistemas, instale Tesseract com português. É possível configurar `EXAM_TESSERACT_CMD` e `EXAM_OCR_LANG` nas configurações Django. Os arquivos são processados localmente, sem serviço externo de reconhecimento.

Validação automatizada: `python manage.py test ColorAdminApp.tests.tests_music_exams ColorAdminApp.tests.tests_exam_import` e `python manage.py check`.

## Consulta dos registros

Os resultados são agrupados por administração, categoria (músicos ou organistas) e data do exame. Cotia/Caucaia/VGP e Santana/Pirapora mantêm seus agrupamentos. Os grupos começam recolhidos; as pessoas são renderizadas ao abrir uma data. Dentro da data, a ordem é sempre RJM, Culto Oficial, Oficialização e exames especiais, com ordenação alfabética dentro de cada nível. Exames especiais e emergenciais recebem destaque próprio.

Exames de até 100 registros carregam todas as pessoas ao abrir a data; assim, um exame com 23 alunas mostra os 23 registros na mesma lista. Acima disso, a opção inicial é de 50 por página. O seletor permite alternar entre todos, 10, 25 ou 50. Os atalhos de nível mostram a quantidade total e abrem diretamente, por exemplo, as cinco alunas de Oficialização. A seleção é preservada ao alternar níveis ou páginas. **Selecionar lista** considera o nível atualmente exibido; a exclusão do exame inteiro continua considerando todos os níveis daquela data e informa a quantidade na confirmação. A busca por nome abre os resultados correspondentes. A exportação mantém os filtros da lista.

Os resultados são exibidos como **Aprovada** para organistas e **Aprovado** para músicos; o código interno permanece canônico. A página é entregue sem cache de HTML e o script de apresentação é versionado para evitar rótulos desatualizados após atualizações.

O formulário pesquisa alunos no servidor a partir de duas letras, com até 30 resultados por consulta e escopo aplicado no servidor. Não carrega a relação regional inteira em um seletor. Na visualização, o campo **Prova ou carta digitalizada** apresenta o documento e o botão **Anexar** ou **Substituir**. Escolher um arquivo mostra o nome para conferência; o envio ocorre somente em **Salvar anexo**, sem alterar resultado, data ou evolução do aluno. As observações exibem apenas anotações manuais; os vínculos antigos de agenda são recuperados sem mostrar os metadados no campo.

O modal reutiliza os estilos compartilhados de **Detalhes da atividade**, em `static/css/musicalizacao-activities.css`: cabeçalho azul/verde, resumo de nível/resultado/data, blocos de identificação com ícones e rodapé fixo. A visualização apresenta uma ficha, sem controles desabilitados aparentes. **Editar exame** alterna para os campos editáveis no mesmo modal, preservando os valores e funcionando independentemente do anexo. **Fechar** e **Cancelar** usam vermelho e ícone de fechar; **Salvar** conclui a edição.

## Exclusão de registros de um exame

Ao abrir uma administração, categoria e data, marque pessoas individualmente ou use o checkbox do cabeçalho para selecionar apenas a página atual. A seleção permanece ao trocar de página. **Selecionar lista** marca todos os registros da lista filtrada desse exame; **Limpar seleção** desmarca o grupo.

**Excluir selecionados** remove apenas os IDs escolhidos. **Excluir grupo inteiro** considera todos os registros acessíveis da mesma administração, categoria e data, inclusive os que estiverem em outras páginas ou fora dos filtros atuais. A confirmação informa o contexto e a quantidade obtida do servidor antes de qualquer exclusão.

O servidor valida o escopo e o grupo, emite uma confirmação vinculada à sessão e revalida o grupo antes de cada lote de até 20 registros. Novos registros ou alterações detectadas depois da prévia exigem nova confirmação. Os registros individuais e seus lançamentos compartilhados são removidos; em falha, apenas os lançamentos de exames confirmados como ainda existentes são recompostos. O painel é recarregado para conferir os restantes antes de repetir uma operação interrompida.

Os cadastros e o nível atual dos alunos são preservados. A remoção do exame retira seu marco do histórico e permite importar novamente o documento, reutilizando os cadastros existentes. A auditoria existente de exclusões permanece aplicável. Esta ação opera sobre os exames individuais; não elimina os consolidados antigos sem registros nominais.

Testes de exclusão: `python manage.py test ColorAdminApp.tests.tests_exam_group_delete`.
