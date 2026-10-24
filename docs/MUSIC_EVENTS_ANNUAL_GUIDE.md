# Acompanhamento anual dos ensaios regionais

Em **Música > Ensaios Regionais > Acompanhamento anual**, selecionar ano e município de origem. A opção **Administração: Cotia / Caucaia / VGP** reúne os três municípios, preservando o local real de comparecimento de cada encarregado. O município de origem é sincronizado com o filtro do painel principal. O ano considera todos os encontros carregados, independentemente do evento individual selecionado.

## O que acompanhar

- Todas as comuns do catálogo institucional acessíveis ao usuário, inclusive as que não têm qualquer presença importada.
- Cadastro SAM atual de músicos e organistas, contemplando Ativo, Alerta e Concluído em todos os níveis.
- Por data: músicos e organistas presentes, respectivos percentuais e situação/local do encarregado.
- Quantos ensaios tiveram músicos, organistas e encarregado de cada comum.
- Filtros para nenhum músico, nenhuma organista, nenhum registro de encarregado e nenhum registro dos três públicos.
- Quantos dos três ensaios regulares do circuito têm dados carregados. Datas não importadas não recebem zero nem NJ.

O circuito regular de Itapevi/Pirapora é janeiro, maio e setembro; Cotia/Caucaia/VGP, Jandira e Fazendinha utilizam março, julho e novembro, conforme a regra já usada pelo histórico do projeto. Convocações explícitas prevalecem sobre essa regra para a comum. Encontros extraordinários usam os locais reconhecidos, sem inventar convocação. Datas simultâneas são uma oportunidade, mesmo quando importadas como eventos separados.

Presenças com ID SAM ou UUID de origem estável são deduplicadas na mesma data entre os locais. Nomes iguais não são uma identidade suficiente para fundir pessoas. O local do encarregado continua registrando todos os locais comprovados em sua presença/conferência.

## Leitura correta dos dados

Os nomes das comuns são conciliados com o código oficial do catálogo. A normalização trata abreviações de endereço, pontuação, acentos, sufixos municipais, grafias locais conhecidas e códigos antigos acompanhados de um nome cadastral inequívoco. Cotia/Caucaia/VGP permitem a procura da mesma comum dentro da administração conjunta. Nomes curtos ambíguos, como Santa Rita quando há mais de uma comum possível, continuam sinalizados para conferência. Os registros de origem são preservados.

Na matriz PDF, a identificação apresenta nome da comum, código e encarregado local cadastrado. Músicos, Organistas e Encarregado local são escritos por extenso nas quantidades e na participação anual. A faixa de contexto identifica município de origem, ano e cobertura dos três ensaios.

**Sem participação registrada** é uma pendência de acompanhamento, não uma comprovação automática de ausência. O relatório preserva **Não informado**, **J**, **NJ**, **SE** e **EF**, sem transformar falta de conferência em NJ. Comuns não conciliadas na lista de presença são sinalizadas antes de concluir uma ausência.

Percentual por ensaio = presentes da comum / cadastro SAM atual da categoria. Percentual anual = soma de presenças / (cadastro atual da categoria × datas carregadas do circuito). São oportunidades de presença, não pessoas únicas ao longo do ano. O denominador não é repetido por local físico. População zero ou base não disponível não produz percentual artificial.

O cadastro atual é identificado expressamente: ele não é uma captura histórica de janeiro ou de anos anteriores. O arquivo mostra emissão e responsável. O sistema não modifica bases SAM, presenças ou justificativas ao consultar ou exportar.

## PDF

O botão **PDF do acompanhamento** gera a matriz anual e, em seguida, a grade detalhada e o resumo por encontro. O botão **PDF deste ensaio** gera somente o encontro, considerando os municípios escolhidos. Os botões **PDF por município** geram arquivos individuais. O filtro de acompanhamento também é aplicado à exportação.

A grade detalhada reproduz o modelo explicitamente solicitado no arquivo `RELATÓRIO_EnR_UNIFICADO_16.11.25.pdf`: brasão fornecido, título, município na lateral, grupos Presentes no Ensaio / Números por Localidade, local/situação do encarregado, músicos, organistas, total musical, cadastro e percentuais. A identidade desta grade segue a referência expressamente pedida pelo usuário; a matriz anual adicional segue o cabeçalho institucional de `REPORT_EXPORT_STANDARD.md`.

Não copiar totais ou gráficos antigos do PDF: todos os números, resumos e gráficos são calculados a partir das presenças e conferências consultadas. Cargos podem se sobrepor à categoria musical e não entram novamente no total de pessoas.

## Desempenho e acesso

A consulta anual só inicia ao abrir sua aba. Fontes independentes são consultadas em paralelo e mantidas no servidor por até 60 segundos para troca de município e exportação. Escopo e filtros são reaplicados a cada requisição; nenhum resultado nominal de outro usuário é reutilizado. Criação, importação e conferência invalidam essas fontes. **Atualizar ano** força uma nova consulta de presenças; o cadastro SAM mantém o cache de cinco minutos já utilizado no projeto.

Não há migração SQL nova. As migrações existentes de eventos, convocações e conferência dos encarregados continuam sendo utilizadas.


## Fechamento e documento original

O painel de participação substitui o resumo de gráficos da exportação por ensaio. Não apresenta legenda: valores, datas e situações são identificados diretamente. Compara indicadores, músicos e organistas com a última data carregada e aplicável ao mesmo circuito no ano, mantendo os mesmos filtros de município e comum. Datas de outro circuito não entram na comparação. Sem data anterior, o painel informa essa condição; base anterior zero não é convertida em crescimento percentual artificial. A faixa inferior mostra comuns representadas, comuns sem os três públicos e a evolução do público do recorte. Esses números são por origem, separados do público físico apresentado no fechamento.

A situação do encarregado segue o modelo: **PRESENTE**, **J — JUSTIFICOU**, **NJ — NÃO JUSTIFICOU**, **SE — SEM ENCARREGADO** e **EF — ENFERMO**. SE e EF são preservados quando registrados, inclusive no formulário, filtros, resumos e exportações. A legenda colorida acompanha cada página da grade de presenças. Os dados legados continuam preservados para auditoria.

Os destinos obedecem ao calendário regular: janeiro/maio/setembro em Itapevi e Pirapora; março/julho/novembro nos demais municípios. Novas importações e conferências manuais rejeitam destinos incompatíveis antes da gravação. O dado original não é alterado automaticamente.

Os relatórios gerados usam textos em maiúsculas e cabeçalho institucional. Conforme o modelo fornecido, a grade possui dois grupos integrados e alinhados: **PRESENTES NO ENSAIO** (encarregado, músicos, organistas e total) e **CADASTRO SAM — COMUM DE ORIGEM** (bases e percentuais). A escala percentual permanece verde.

O título e os totais do PDF usam o município de origem selecionado, nunca os destinos de comparecimento. Presenças de uma comum de Itapevi em outro local continuam pertencendo a Itapevi; o destino permanece visível apenas como local de comparecimento.

O fechamento geral considera o público físico do local, de todas as origens, e identifica sua fonte em uma linha. Os documentos originais não são anexados aos PDFs gerados. Os originais e os totais transcritos nos arquivos `*_closing.json` permanecem em `docs/references/music_events` para conferência. Os totais do original não alteram as presenças por comum nem os percentuais sobre SAM.

O subtotal de origem permanece no resumo das comuns. Sem original, o fechamento utiliza a lista nominal do local quando disponível. Instrumentos seguem a ordem do modelo, com cordas, madeiras e metais identificados por faixas coloridas; órgão/organistas e acordeon precedem os naipes. A fonte e as colunas foram ampliadas; o bloco de notas de conciliação não é impresso.
