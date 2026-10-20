# Música — Ensaios regionais e reuniões técnicas

## Entrega e situação

Análise das cinco referências fornecidas, modelo SQL e especificação funcional da nova página. O responsável informou que aplicou a migração 029. A aplicação agora possui a rota `/musica/eventos/` e o menu **Música > Ensaios e Reuniões Técnicas**, com filtros, lista de eventos, consulta da frequência por comum e resumo por local. A administração regional pode criar rascunhos quando houver uma base SAM homologada. O conector da base, configuração de locais/convocações, operação de presenças, importador e exportadores ainda não estão implementados. O restante deste documento descreve o escopo completo planejado.

Decisão do responsável pelo projeto: a base esperada contempla **músicos e organistas ativos de todos os níveis**. RTs consideram apenas o público da família selecionada. A categoria musical de uma pessoa é independente de seu cargo: um encarregado que participa como músico é uma pessoa, com categoria Músico e cargo Encarregado Local.

## O que as referências exigem

| Referência | Conteúdo relevante | Consequência no sistema |
| --- | --- | --- |
| EnR unificado de 16/11/2025 | Comuns de Caucaia, Cotia e VGP; local de comparecimento; presentes e cadastro por comum; percentuais; situação dos encarregados; resumo por local | Evento administrativo único com vários encontros e vínculo explícito das comuns convocadas |
| EnR unificado Itapevi de 18/01/2026 | Músicos e organistas por comum, incluindo zeros; presentes/justificados/não justificados; totais administrativos | Manter todas as comuns convocadas, mesmo sem presença; situação do encarregado independente da presença musical |
| EnR Itapevi de 17/05/2026 | Presidência, atendimentos, hino cantado, Palavra; instrumentos, famílias, ministérios, apoio e irmandade; hinos ensaiados | Relatório administrativo separado da frequência, alimentado pelo mesmo conjunto validado |
| DB de Cordas Cotia de 29/08/2026 | Aba `Registros` nominal com UUID, comum, cidade, cargo, instrumento, família, nível, local, horário, operador e sincronização | Importação nominal com prévia, vínculo SAM, trilha de origem e prevenção de repetição |
| DB EnR de 15/03/2026 | Aba `Dados` com o mesmo formato nominal e diferentes locais; abas de resumos, SAM e encarregados | Importador deve reconhecer o cabeçalho, não depender de uma aba chamada `Registros` |

Achados que devem aparecer na conferência de importação:

- O arquivo de agosto tem 104 registros nominais com UUID distinto na aba `Registros`. Há famílias Cordas, Madeiras, Metais e Teclado; o nome do arquivo não autoriza descartar os demais presentes nem prova a família efetiva do encontro.
- Existem abas auxiliares com dados antigos, inclusive de 2024, e títulos de outro evento. Não importar todas as abas nem confiar em resumos ou gráficos armazenados.
- O PDF de maio informa 320 organistas no total e 310 no gráfico. Todos os números e gráficos novos devem derivar da mesma consulta validada.
- Em março há registro com `DATA_ENSAIO` em 14/03, embora o arquivo seja de 15/03. Exigir confirmação explícita da data administrativa do evento e conservar o timestamp original. Não converter silenciosamente uma data divergente.
- O arquivo de março contém uma aba `SAM` identificada como lista de igrejas com cadastro desatualizado. Ela **não é uma população SAM completa** e não pode fornecer o denominador.
- Há nomes repetidos em relações auxiliares de encarregados. Nome, cargo e comum são evidências de conciliação, não uma identidade individual garantida.

## Organização da página

Menu: **Música > Ensaios e Reuniões Técnicas**. Rota proposta: `/musica/eventos/`.

Reutilizar a estrutura visual de `music_exams.html` e dos painéis operacionais existentes: banner institucional do módulo, cartão de filtros, indicadores e tabela principal. Usar componentes de formulário já presentes no projeto.

1. **Eventos:** período, tipo, família, local do encontro, município de origem, comum e situação. A tabela apresenta data, título, tipo/família, locais, participantes, cobertura SAM e estado. Ações: abrir, novo evento, importar presenças, Excel e PDF.
2. **Detalhe do evento:** abas Visão geral, Frequência por comum, Presenças, Administração e Conferência. O mesmo recorte deve alimentar tela e exportações.
3. **Novo evento:** data, título, Ensaio Regional ou RT, família, base SAM homologada e comuns convocadas. Incluir um ou mais locais, com município e comum sede. Ensaio Regional usa público Geral. RT permite Geral, Cordas, Madeiras, Metais ou Organistas.
4. **Presenças:** busca por nome, ID SAM ou comum; seleção da pessoa; escolha do local de comparecimento. Mostrar categoria, instrumento, nível, cargo e comum de origem. Pendências de vínculo devem ficar visíveis antes de confirmar.
5. **Administração:** presidência, atendimentos, hino cantado, Palavra, hinos ensaiados e quantidades complementares de irmandade/apoio em cada local. A situação do encarregado fica na comum convocada: Presente, Justificou, Não justificou, Sem encarregado, Enfermo ou Não informado.

Indicadores: músicos presentes, organistas presentes, percentual de frequência de cada categoria, comuns com presença e pendências de conciliação. Separar claramente **presentes administrativos** de **presentes elegíveis para o percentual**. Não apresentar um número como se os dois conceitos fossem iguais.

Ao selecionar um local, a tabela de frequência continua agrupada pela comum de origem e informa o recorte. O consolidado considera comparecimento em qualquer local do evento. A comum pode ter pessoas em Cotia e Caucaia no mesmo dia sem duplicar o cadastro esperado.

## Identidades e histórico

- `musica_evento_comuns`: código BR estável, nome, município e regional. Conciliar com o catálogo institucional existente; não substituir o cadastro oficial de congregações.
- `musica_evento_bases`: captura do cadastro SAM, com referência, origem, hash opcional do arquivo e homologador.
- `musica_evento_base_cobertura`: uma linha para cada comum coberta, inclusive comuns com zero pessoas; nome/município históricos e quantidade verificada na fonte.
- `musica_evento_base_pessoas`: ID SAM, comum, categoria, família, instrumento, nível, cargo e situação ativa. Um ID SAM aparece uma vez em cada captura.
- `musica_eventos`: o evento administrativo, com base histórica fixa e critério `ATIVOS_TODOS_NIVEIS`.
- `musica_evento_locais`: encontros físicos simultâneos e seus metadados administrativos.
- `musica_evento_convocacoes`: comuns convidadas e local de referência. Chave única evento + comum evita duplicar o denominador.
- `musica_evento_presencas`: participante nominal, local efetivo, situação, origem e autoria autenticada. Chave única evento + identidade evita presença duplicada entre locais.
- `musica_evento_auditoria`: criação e alterações do evento/presença, antes/depois e usuário.

Separar sempre três identidades: ID SAM da pessoa, UUID da linha importada e ID do usuário que opera o sistema. `REGISTRADO_POR` legado é evidência do arquivo e não substitui o operador autenticado da importação.

O nome e o município da comum ficam preservados na cobertura da captura. A base homologada é imutável. Alterações posteriores no SAM exigem nova captura e não reescrevem eventos passados. A base, a data e o público do evento também não podem ser trocados após sua criação; um evento configurado incorretamente deve ser substituído antes dos lançamentos.

Uma base importada hoje pode servir de referência explicitamente identificada para um evento antigo, mas não pode ser apresentada como cadastro vigente naquela data. A tela e o relatório devem exibir a referência da base usada.

## Regra de frequência

**Frequência da comum = presentes elegíveis vinculados ao SAM ÷ população elegível da comum × 100.**

Elegível significa: ativo na captura, de qualquer nível, com comum convocada e pertencente ao público do evento. Nos ensaios gerais, músicos e organistas entram nas respectivas categorias. Na RT de Cordas entram apenas músicos de Cordas; organistas presentes continuam no resumo administrativo, mas não entram no percentual dessa RT. Para RT de Organistas, o inverso se aplica.

Exemplo: comum com 40 músicos ativos e 10 organistas ativos; comparecem 12 músicos e 4 organistas. Frequências: **30%** e **40%**. Se os 12 músicos estiverem divididos entre Cotia e Caucaia, continuam sendo 12/40 no consolidado.

Para duas comuns com 1/2 e 9/90 músicos, o consolidado é 10/92 = **10,87%**, nunca a média de 50% e 10%. Repetir o denominador em cada local produziria um resultado incorreto.

Regras de ausência de dados:

- Base completa com população positiva e nenhuma presença: **0%**.
- Base completa com população zero: **Não se aplica** (`NULL` no SQL).
- Captura não homologada ou cobertura ausente/incompleta: **Base não validada**, sem percentual. Nunca converter em 0%.
- Pessoa sem vínculo SAM confirmado: aparece na lista e na contagem administrativa; não entra no numerador de frequência até a conciliação.
- Visitante de comum não convocada: entra no resumo administrativo; não entra no numerador nem no denominador das comuns convocadas.
- Pessoa inativa na captura que compareceu: entra no resumo administrativo e gera revisão cadastral; não altera automaticamente a população elegível.
- Família desconhecida: sinalizar na conferência. Não inferir a família pelo cargo, nome da pessoa ou arquivo.

Uma pessoa tem uma categoria principal de presença, mas pode ter um cargo. As análises por cargo/instrumento são dimensões sobrepostas e não devem ser somadas para formar o total geral. O total geral é o número de pessoas presentes, acrescido apenas das contagens complementares explicitamente não nominais.

Não usar a ausência de histórico pedagógico do GEM para presumir que um músico é inativo. O status ativo deve vir do cadastro individual SAM validado.

## Integração SAM e importação dos arquivos

O projeto já tem espelho pedagógico e rotinas de turmas/históricos SAM. Isso não comprova que o espelho contém a população completa de músicos e organistas ativos da Regional. A integração desse módulo deve usar o cadastro individual completo com ID estável, comum, status, nível, instrumento e categoria, verificando todas as páginas e os totais por comum.

Fluxo da base: capturar em área de preparação, normalizar códigos/famílias, verificar IDs duplicados e comuns não mapeadas, reconciliar a contagem com a fonte e homologar. A homologação congela o conteúdo. A SQL exige cobertura e quantidade conciliadas; a confirmação de que a fonte foi percorrida integralmente cabe ao conector/importador e ao responsável pela homologação.

Fluxo das presenças:

1. Selecionar evento e local ou mapear explicitamente `LOCAL_ENSAIO` para os locais existentes. Aceitar `Registros` de agosto e `Dados` de março por detecção do cabeçalho completo.
2. Ler somente a aba nominal escolhida. Exibir quantidades, período encontrado, locais, famílias, duplicidades e linhas rejeitadas antes de gravar.
3. Preservar UUID e hash de origem. Reimportar o mesmo UUID no mesmo evento não cria outra presença. UUIDs diferentes da mesma pessoa também são deduplicados pelo vínculo SAM.
4. Conciliar por ID SAM quando disponível. Na ausência de ID, oferecer candidatos por código da comum + nome normalizado e instrumento. Casos ambíguos exigem escolha; não unir homônimos automaticamente.
5. Apresentar comuns antigas/sem código para mapeamento explícito. Variantes como Central de Cotia / Vila Monte Serrat devem apontar para o mesmo código institucional, quando confirmado.
6. Conferir data administrativa versus timestamp original. Preservar `REGISTRADO_POR`, `REGISTRADO EM`/`DATA_ENSAIO`, nível, instrumento e observações como origem, sem substituir a autoria atual.
7. Gravar o lote validado em transação pelo backend e devolver o resultado por linha. Manter o arquivo original em armazenamento privado; rejeitar upload excessivo, arquivo inválido e expansão ZIP excessiva.

O arquivo de Cordas demonstra outra regra: cargo `SECRETÁRIO DA MÚSICA`, `INSTRUTOR` ou `ENCARREGADO LOCAL` pode vir com instrumento. O importador deve propor a categoria musical a partir do vínculo SAM e confirmar se a pessoa participou como músico; não contar automaticamente todos esses cargos como Ministério nem contar a mesma pessoa em duas categorias.

## Exportações administrativas

Implementar dois relatórios no detalhe do evento:

**Frequência por comum:** município de origem, código e nome da comum, situação do encarregado, músicos presentes elegíveis, músicos na base, percentual de músicos, organistas presentes elegíveis, organistas na base e percentual de organistas. Incluir comuns com zero presença, subtotais por município e total ponderado. Informar data/referência da base e critério todos os níveis. Oferecer consolidado ou recorte por local, com o numerador e o denominador claramente identificados.

**Relatório administrativo:** dados do atendimento por local; totais reais de músicos/organistas; contagens por instrumento, família e cargo; hinos ensaiados; ministério, apoio e irmandade; visitantes e participantes sem vínculo. O consolidado soma pessoas únicas, sem somar novamente os cargos musicais.

Excel: abas `Frequência`, `Resumo administrativo` e, quando solicitado, `Presenças`. A nominal exige permissão de acesso. Valores numéricos e datas devem permanecer tipados. Percentuais usam razão numérica com formato `0.0%` ou `0.00%`; divisões sem base válida ficam vazias com motivo explícito. Totais usam componentes, nunca média dos percentuais. Texto externo que começa com `=`, `+`, `-` ou `@` deve ser escrito como texto, sem fórmulas introduzidas pelo upload.

PDF: uma versão de frequência em A4 paisagem e outra administrativa, escolhendo orientação pela largura efetiva das tabelas. Gráficos usam exatamente os mesmos totais das tabelas. A participação por família é composição dos músicos presentes; não é frequência sobre o SAM. Se forem adotadas metas de composição como 50/25/25, identificá-las como metas configuradas, não como percentual esperado de comparecimento.

Reutilizar obrigatoriamente `docs/REPORT_EXPORT_STANDARD.md`:

- PDF com colunas laterais equilibradas, cabeçalho central institucional, módulo **MÚSICA**, título específico e metadados à direita; azul `#1e4b7a`, apoio `#eaf2f8`, tabela na largura útil, linhas alternadas e paginação.
- Excel com cabeçalho institucional mesclado na largura total, módulo/título/recorte/emissão/responsável, azul institucional, filtros, congelamento, larguras e impressão configuradas em todas as abas.
- Datas do evento `dd/mm/AAAA`; emissão/auditoria `dd/mm/AAAA HH:mm`, fuso America/Sao_Paulo; arquivos `dd-mm-AAAA_HH-mm`.
- Responsável pela emissão vem da sessão autenticada; não do campo legado do arquivo.

Referências canônicas conferidas: `generateStandardPdf` em `templates/pages/musicalizacao.html` e `export_report` em `modules/gem_sync_admin.py` (o caminho antigo na norma foi reorganizado para `modules`). Os exportadores atuais reutilizam essa identidade, com frequência por comum, subtotais municipais, resumo por local, instrumentos, famílias e cargos.

## Backend, escopo e autoria

Rotas propostas para a implementação:

| Método e rota | Operação |
| --- | --- |
| GET `/musica/eventos/` | Página e filtros |
| GET/POST `/musica/eventos/api/eventos/` | Listar/criar rascunho |
| GET/PATCH `/musica/eventos/api/eventos/<id>/` | Detalhe, abrir/encerrar/reabrir com justificativa |
| POST `/musica/eventos/api/bases/capturar/` | Preparar captura SAM |
| POST `/musica/eventos/api/bases/<id>/homologar/` | Homologar cobertura conciliada |
| POST `/musica/eventos/api/eventos/<id>/importacao/previa/` | Preparar e conferir o lote, sem gravar presenças |
| POST `/musica/eventos/api/eventos/<id>/importacao/confirmar/` | Gravar lote revisado atomicamente |
| POST/PATCH `/musica/eventos/api/eventos/<id>/presencas/` | Registrar/corrigir/cancelar presença |
| GET `/musica/eventos/api/painel/` | Indicadores e tabelas no recorte autorizado |
| GET `/musica/eventos/exportar-excel/` | Excel com os mesmos parâmetros do painel |
| GET `/musica/eventos/exportar-pdf/` | PDF com os mesmos parâmetros do painel |

Todas as operações exigem sessão autenticada, pasta Música segundo a política vigente do projeto e escopo territorial. O projeto hoje usa a autorização da Musicalização em Exames/GEM; o novo módulo deve seguir essa convenção enquanto não houver uma permissão Música independente. Não ampliar `VALID_MODULES` sem migração de permissões.

Regional/global administra evento consolidado, base, convocações e fechamento. Municipal/local registra e consulta dentro de sua área de origem. O local físico do encontro não concede acesso à lista de outras comuns. Aplicar escopo antes de agregar ou exportar e antes de retornar nomes de visitantes. O servidor deve validar tanto a origem da pessoa quanto a permissão de atuar no encontro.

Campos de autor são preenchidos pelo servidor com ID e nome da sessão, ignorando valores enviados pelo navegador. A SQL bloqueia alteração da autoria original e audita criação/edição de eventos e presenças. Metadados de locais e convocação devem ser alterados pelo backend em transação, com auditoria complementar da operação e bloqueio para evento encerrado. Não há DELETE exposto: cancelamentos preservam a trilha.

RLS fica habilitada sem políticas para `anon`/`authenticated`; tabelas e views só são usadas pelo backend com credencial de serviço. Views usam `security_invoker` (PostgreSQL 15+). Isso **não substitui** a autorização Django: `service_role` ignora RLS. Nunca expor a chave nem consultar as views sem aplicar escopo.

## Homologação e sequência de implementação

1. Aplicar a migração em banco de homologação PostgreSQL 15+ e executar `scripts/validation/029_musica_eventos_frequencia_smoke.sql`. O script de conferência desfaz seus dados ao terminar.
2. Conectar o cadastro SAM completo, conferir cobertura/IDs e homologar uma captura. Não importar as abas de exemplo como se fossem esse cadastro.
3. Implementar a página e as APIs acima, com gravações de lote em transação, autorização, proteção CSRF, estado encerrado, prévia de importação e vínculo nominal revisado.
4. Implementar Excel/PDF com a norma institucional e gerar arquivos de amostra. Renderizar e inspecionar cabeçalho, repetição, paginação, colunas, recorte, usuário e datas; comparar com as referências canônicas.
5. Testar simultaneidade Cotia/Caucaia/VGP, homônimos, comum transferida, visitantes, RT por família, todos os níveis, ausência de base, zero elegíveis, reimportação e duplicidade entre locais. Testar a autoria pela sessão real, além dos testes automatizados.
6. Só depois publicar o menu e executar a migração no ambiente de uso.

Estado atual: painel administrativo, indicadores, filtros de evento/período/origem/local, importação AppCont com prévia e transação, consulta agrupada por município/comum, rascunhos e exportadores Excel/PDF implementados. O filtro separa município de origem do local físico do encontro. RTs são Geral (todos os naipes), Cordas, Madeiras e Metais. A presença do encarregado pode ser evidenciada pelo cargo nominal; ausência não é presumida. Continuam pendentes o conector do cadastro SAM completo, as convocações e a conciliação nominal, necessários para os percentuais, e a edição manual dos dados administrativos. Nenhuma informação histórica foi preenchida por suposição e nenhum arquivo de referência foi alterado.

Validação realizada: a migração e o smoke test passaram na análise sintática PostgreSQL e PL/pgSQL com `pglast`; `python manage.py check` não apresentou problemas. Isso não executa tabelas, permissões, triggers ou cálculos em um servidor. O smoke test foi escrito, mas não executado: não havia PostgreSQL local disponível. Não considerar a migração homologada em banco por causa da análise sintática.
