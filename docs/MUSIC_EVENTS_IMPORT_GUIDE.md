# Como testar a importação de ensaios e RTs

## Preparação

1. A migração 029 já foi aplicada pelo responsável. Aplicar também **`scripts/migrations/030_musica_eventos_importacao_appcont.sql`**, que permite importar contagens sem inventar uma base SAM.
2. Atualizar a aplicação e recarregar a página com **Ctrl + F5**. O menu é **Música > Ensaios e RTs** (`/musica/eventos/`).
3. Usar uma conta regional/global autorizada na pasta Música. A importação envolve vários municípios e não é liberada a perfis locais/municipais.

## Importação do arquivo de referência

1. Clicar em **Importar Excel** e selecionar `DB_EnR_20.09.2026.xlsx`.
2. Aguardar a prévia. O sistema identifica a aba nominal pelo cabeçalho, sem importar resumos, gráficos ou abas antigas.
3. Conferir os locais, a classificação proposta, as duplicidades e as datas originais. Confirmar **20/09/2026** como data administrativa. As datas originais divergentes ficam preservadas.
4. Manter **Ensaio regional / Geral**, informar o título e marcar a confirmação de conferência.
5. Clicar em **Confirmar importação**. A aplicação grava o evento, seus locais, os participantes e o recibo do arquivo em uma transação.
6. Abrir o evento e comparar o resumo por local, as contagens por comum de origem e as distribuições por instrumento, família e cargo.

Reenviar o mesmo arquivo conserva o evento existente, identificado pelo hash do conteúdo. **Um arquivo editado tem outro hash e gera outro evento** nesta versão; não usá-lo para corrigir um evento já importado. A atualização de eventos por lote será um fluxo separado.

## Valores de controle da planilha recebida

Leitura da aba `Dados`, mantendo a última ocorrência de cada UUID repetido da mesma pessoa/local:

| Conferência | Valor |
| --- | ---: |
| Linhas nominais recebidas | 1.055 |
| Repetições de UUID | 5 |
| Registros únicos importáveis | 1.050 |
| Local Itapevi | 846 |
| Local Pirapora | 204 |
| Músicos, classificação proposta | 558 |
| Organistas, classificação proposta | 139 |
| Ministério | 25 |
| Apoio | 31 |
| Irmandade | 297 |

Na entrada há 1.051 linhas com data 20/09/2026, três com 19/09/2026 e uma com 15/09/2026. Essas contagens de datas são anteriores à deduplicação dos UUIDs.

O cargo e o instrumento são dimensões separadas: um instrutor tocando violino conta como músico e aparece também na distribuição por cargo. Não somar os cargos novamente ao total de participantes. Órgão/funções de organistas contam como organistas na proposta de classificação; registros sem instrumento são classificados pelo cargo. A prévia exige que o operador confira esse resultado.

UUID repetido com nome ou local diferente bloqueia a importação. Nomes iguais com UUIDs diferentes são sinalizados como possíveis duplicidades/homônimos e **preservados**, sem presumir que sejam a mesma pessoa. Portanto, 1.050 é o total de registros únicos pelo UUID do app, e não uma afirmação de identidade pessoal conciliada com o SAM.

## O que já pode ser testado

- Importação pelo navegador com prévia e confirmação.
- Persistência do evento, locais e presenças, com autoria do usuário autenticado.
- Resumo administrativo por local e contagem por comum e município informados.
- Distribuições por instrumento, família e cargo.
- Reimportação do mesmo arquivo sem duplicação.
- Preservação de dados de origem, incluindo operador legado e data/hora original. A data/hora da planilha é preservada como texto de origem, sem pressupor um fuso que ela não informa.

A prévia fica disponível por 30 minutos e vinculada ao usuário que enviou o arquivo. Se expirar ou o servidor reiniciar, selecionar o arquivo novamente. Uma falha de conexão na confirmação pode ocorrer depois do commit; repetir a confirmação é seguro para o mesmo arquivo.

## Próxima parte: frequência sobre o SAM e relatórios

### Presença dos Encarregados Locais

Aplicar a migração **031_musica_eventos_encarregados.sql** para salvar essa conferência. A seção **Presença dos Encarregados Locais** apresenta os totais por município e a relação por evento/comum, independentemente de uma base SAM homologada.

- **Presente:** identificado pela presença nominal com cargo Encarregado Local, ou confirmado administrativamente. O relatório apresenta o local em que compareceu.
- **J · Justificou:** registro manual, com justificativa ou referência recebida obrigatória.
- **NJ · Não justificou:** informado explicitamente após conferência.
- **Não informado:** ainda não foi conferido. Não vira NJ automaticamente.

Usar **Conferir** na linha da comum ou **Registrar conferência** para incluir uma comum sem participantes na planilha. As alterações registram o usuário autenticado e conservam auditoria. Eventos encerrados não permitem edição.

Os botões **Excel** e **PDF** nessa seção exportam apenas o relatório dos encarregados, com relação por comum e resumo por município. Os filtros do painel são respeitados. Um filtro de local de comparecimento mostra os presentes naquele local; retirar esse filtro para analisar também as justificativas e os NJ. As quantidades representam conferências de comuns por evento, não pessoas distintas no período.

### Leitura do painel de apresentação

O título do módulo é **Ensaios Regionais e RTs**. A barra principal de desktop reúne ano, mês, período, município, comum e exportação em uma linha. Evento, tipo de encontro, local e abrangência ficam em **Mais filtros**.

Os gráficos separam dois conceitos: a participação musical compara músicos e organistas; a composição por naipe usa somente músicos e apresenta Cordas, Madeiras e Metais, com outros instrumentos identificados à parte.

Os cartões de evolução usam exclusivamente encontros importados, em ordem de data, comparando o mesmo tipo de encontro e município de origem. Mostram músicos e organistas do último encontro, variação sobre o encontro anterior e distância do pico. Para um evento selecionado, o histórico termina na data desse evento; filtros de período e origem também são respeitados. Um único encontro produz apenas um ponto e nenhuma taxa de evolução. As imagens de apresentação servem como referência visual e não foram convertidas em registros históricos no banco.

As contagens do AppCont são o **numerador administrativo**. A planilha de presenças não informa o total de músicos e organistas ativos ausentes e, portanto, não fornece o denominador da frequência.

Para calcular os percentuais, é preciso capturar o cadastro individual completo dos sete municípios (ativos de todos os níveis), homologar a cobertura por comum, configurar as convocações e conciliar cada participante com seu ID SAM. Até isso acontecer, a página informa que os percentuais estão indisponíveis; não mostra 0% indevido.

Os dados persistidos alimentam `musica_evento_presencas`, `musica_evento_resumo_local` e o recibo em `musica_evento_importacoes`. Eles são a base para os exportadores administrativos. O painel administrativo agora oferece filtros por evento, período, tipo de RT, municípios de origem, comuns, local do encontro e abrangência. Excel e PDF exportam o mesmo recorte, com frequência por comum, resumo por local, instrumentos, famílias e cargos, seguindo `docs/REPORT_EXPORT_STANDARD.md`. Campos de cadastro e percentuais permanecem sem valor até a base SAM ser vinculada.

Não importar a aba `SAM` da planilha como população total: ela é uma lista de cadastro desatualizado. Visitantes permanecem no relatório administrativo e não devem aumentar a população esperada das comuns convocadas.

## Validação técnica

Os testes Python cobrem parser, UUID repetido, homônimos, fórmulas proibidas, classificação, permissões e autoria. O script `scripts/validation/030_musica_eventos_importacao_smoke.sql` testa a transação, os totais e a reimportação em banco de homologação, com rollback ao terminar. Ele não deve ser confundido com uma importação do arquivo real.


### Prioridade territorial e leitura administrativa

O painel e suas exportações abrem em **Sete municípios da Regional**: Caucaia do Alto, Cotia, Itapevi, Jandira, Santana de Parnaíba (Fazendinha), Pirapora do Bom Jesus (Parque Laranjeiras II) e Vargem Grande Paulista. Limpar filtros mantém esse padrão. Em Mais filtros, Origem permite consultar visitantes ou reunir todos explicitamente. Nenhuma presença importada é excluída do banco.

O quadro territorial mostra músicos, organistas, encarregados locais nominalmente presentes, ministério por cargo e conferências de comuns (presente/J/NJ). Conferências não são pessoas: dois encarregados de uma mesma comum continuam sendo uma única conferência. Ministério por cargo inclui ancião, diácono e cooperadores, inclusive quando também tocam instrumento. Essa dimensão se sobrepõe à musical e não deve ser somada ao total geral. Os demais cargos são detalhados no quadro próprio.

A evolução municipal usa **origem**, mesmo que a pessoa tenha participado em outro local. Comum sem presença no arquivo não prova ausência; município sem registro não recebe um ponto histórico zero artificial. Local do encontro segue como filtro separado. Não há meta de composição musical presumida a partir da referência: as porcentagens de naipe descrevem a composição observada, não frequência sobre o SAM.


### Regra obrigatória de comparação entre Ensaios Regionais

São circuitos distintos: março/julho/novembro (Cotia, Caucaia do Alto, Vargem Grande Paulista, Jandira e Fazendinha) e janeiro/maio/setembro (Itapevi e Parque Laranjeiras II). O total de um circuito nunca é comparado ao total do outro. O KPI consolidado exige mesmo tipo, circuito e conjunto de locais importados. Se houver vários circuitos no recorte sem evento selecionado, não há tendência consolidada.

No histórico municipal, participações em ensaios do outro circuito não constituem um novo ensaio daquele município. Um único encontro por município/local não permite crescimento, queda nem distância percentual do pico. Datas fora do calendário regular não são automaticamente consideradas equivalentes. Eventos extraordinários exigem futura classificação explícita para comparação. As contagens continuam disponíveis independentemente da possibilidade de comparar.


### Identificação das comuns e cadastro já existente

As leituras do painel, histórico e relatórios usam o mesmo resolvedor do catálogo `visitas_comuns`: código BR tem prioridade; descrição sem código exige correspondência única dentro do município. Em Cotia, Lageado/Lajeado/Lanjeado/Lanjado são aliases confirmados de BR-22-2797. Punho Velho é alias confirmado pelo administrador de Moinho Velho (BR-22-0416), somente em Cotia. Não se usa aproximação genérica por nome. Origem sem correspondência é marcada **A conferir**, sem excluir participantes e sem inventar um vínculo.

O cadastro `musica_acompanhamento_aluno` alimenta as colunas **Cadastro SAM atual · Músicos/Organistas**, incluindo todos os níveis e oficializados, com status local Ativo, Alerta e Concluído. Inativo, Excluir, instrumento ausente e A definir não compõem essa referência. Identificadores locais repetidos não são contados duas vezes. A leitura é paginada, tem cache de cinco minutos e respeita o escopo territorial do usuário. A RT filtra a família selecionada.

**Cadastro atual não é população histórica homologada.** Sem captura histórica do evento, o PDF/Excel calculam o percentual operacional sobre o cadastro SAM atual e identificam expressamente que a referência vale na data de emissão. Quando existir base histórica homologada, o percentual passa a usar a base preservada do evento e somente presenças conciliadas com o SAM.

O cabeçalho de exportação mantém instituição, regional, módulo e relatório no centro; página, emissão, recorte, comuns, responsável e escopo do emissor ficam à direita. A faixa de recorte só lista filtros aplicados, sem Todos/Sem limite repetidos.


### Navegação gerencial compacta

Evento e tipo de encontro ficam visíveis no cabeçalho. A barra de período, município, comum e exportação continua em uma linha no desktop. Os KPIs principais são músicos, organistas, comuns representadas e encarregados locais nominalmente presentes.

A aba **Visão geral** reúne um único gráfico de evolução e uma tabela dos sete municípios. O seletor do gráfico escolhe município e tipo; duas linhas na mesma escala mostram músicos e organistas. Sem dois encontros comparáveis, não há indicação de alta ou queda. **Comuns** apresenta uma tabela de seis colunas e paginação de vinte linhas. **Encarregados** mantém a conferência e os relatórios próprios. **Composição e cargos** concentra naipes, instrumentos e cargos em gráficos de barras compactos, com expansão opcional da lista. **Eventos** concentra a administração. As abas não alteram o recorte nem removem dados das exportações.


### PDF para apresentação

**PDF frequência** e a rota PDF sem tipo explícito geram somente a relação de presença por comum no formato do relatório regional: encarregado local, músicos presentes, organistas presentes, total geral, base SAM de músicos e organistas e os respectivos percentuais.

O **PDF de encarregados** continua separado. Ele mostra o encarregado cadastrado, o local de referência da comum, a situação, o local efetivo, J/NJ e um resumo municipal que separa presença no local de referência de presença em outro ensaio da Regional. O Excel geral mantém as tabelas completas em abas. O exportador aceita `relatorio=executivo|comuns|encarregados|composicao`.

Selecionar um evento também limita as séries históricas oferecidas no painel ao circuito e conjunto de locais daquele evento. Um único registro é apresentado como primeiro registro, com data e quantidades; não é desenhado um gráfico sem evolução.


### Gráficos visíveis na visão geral

A visão geral apresenta composição musical em rosca com quantidades e percentuais, barras empilhadas de músicos/organistas nos sete municípios, presenças por encontro e principais instrumentos. Os gráficos não dependem da aba Composição. Os quatro KPIs exibem miniaturas da distribuição municipal, explicitamente identificadas como distribuição, sem sugerir crescimento temporal.

Com um encontro, o painel mostra duas colunas de músicos e organistas na data do registro, informando que não existe série temporal suficiente. Com dois ou mais encontros equivalentes, mostra as duas linhas históricas e a variação sobre o anterior. A composição considera Cordas, Madeiras, Metais, Organistas e outros instrumentos; os percentuais usam o total musical. As barras municipais distinguem valores por categoria e total, permitindo abrir as comuns pelo município.
