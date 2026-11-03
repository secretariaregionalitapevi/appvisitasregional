# Investigação do ensaio regional de 17/05/2026

## Atualização após autorização do responsável

Posteriormente, o responsável determinou que o fechamento público do local Itapevi em 17/05/2026 siga o relatório original: total 2.440, músicos 1.201, organistas 320, irmandade 830 e os demais detalhamentos documentais. Essa exceção histórica está configurada explicitamente em `2026-05-17_itapevi_closing.json`, com a fonte identificada como relatório oficial. A lista nominal não foi completada ou redistribuída; continua sendo a fonte da participação por comum. No quadro geral, o filtro de município agora também limita os locais físicos apresentados, mantendo visitantes desses locais.

Em 01/11/2026, o usuário confirmou que os 73 registros com local Cotia pertencem ao local Itapevi nesse evento. A correção foi aplicada somente ao `local_id` dessas presenças. A conferência posterior confirmou a preservação da comum, município de origem, categoria, instrumento, cargo, nome, situação, UUID de origem e observações. O backup dos IDs e local anterior está em `.backups/correcao_ensaio_17-05-2026/cotia_para_itapevi.json`.

Situação nominal após a correção: Itapevi **2.165**, Pirapora **143**, Cotia **0**, total do evento **2.308**. A diferença entre o total declarado de Itapevi (2.440) e a lista nominal passou a **275**. As tabelas abaixo documentam a investigação **anterior à correção**, para preservar a sequência de evidências.

O responsável também esclareceu que membros do ministério podem participar tocando instrumento. A categoria de contagem permanece única por registro; o cargo é uma dimensão adicional. Duplicidades entre registros nominais distintos não são eliminadas por semelhança de nome.

Investigação realizada em 01/11/2026. Foram lidos o PDF original de Itapevi, a planilha DB_EnR_MAI26.xlsx, os registros existentes no Supabase e o código de importação/agregação. Nenhum dado de produção foi alterado.

## Conclusão

A importação conserva as quantidades da aba nominal fornecida, mas essa aba não fecha com o relatório original. O painel privilegia a origem dos participantes e oculta visitantes por padrão. O fechamento físico declarado não é apresentado como indicador principal. A imagem enviada também mostra um recorte de setembro sob um seletor em maio.

## Fontes e conceitos

- **Local do ensaio:** `LOCAL_ENSAIO`. Informa onde a pessoa compareceu fisicamente. O relatório original de Itapevi inclui todas as origens presentes nesse local.
- **Município de origem:** `CIDADE`, conciliada com o catálogo da comum quando reconhecida. Informa de onde veio a pessoa, independentemente do local do ensaio.
- **Comum de origem:** `COMUM`, conciliada por código e referências do catálogo. Não representa necessariamente a comum onde ocorreu o ensaio.
- **Categoria de contagem:** uma por registro: músico, organista, ministério, apoio ou irmandade.
- **Cargo:** dimensão adicional. Um encarregado ou instrutor com instrumento pode estar contado como músico. Somar cargos novamente causa duplicidade.

## Planilha e banco

O importador seleciona apenas a aba `Dados`, identificada pelos cabeçalhos nominais. As outras abas incluem resumos e dados históricos, inclusive de 2024, e não devem ser somadas à aba nominal.

Foram encontrados 2.308 registros e 2.308 UUIDs distintos. A consulta de produção encontrou os mesmos totais por local e categoria:

| Local informado | Músicos | Organistas | Ministério exclusivo | Apoio | Irmandade | Total |
|---|---:|---:|---:|---:|---:|---:|
| Itapevi | 952 | 326 | 25 | 28 | 761 | 2.092 |
| Pirapora | 96 | 16 | 5 | 4 | 22 | 143 |
| Cotia | 67 | 0 | 1 | 0 | 5 | 73 |
| Total | 1.115 | 342 | 31 | 32 | 788 | 2.308 |

Isso comprova igualdade das contagens analisadas, não a integridade nominal pessoa a pessoa nem que a fonte contenha todo o público efetivo.

## Comparação do local Itapevi com o PDF

| Medida | PDF original | Lista nominal importada | Diferença: PDF menos nominal |
|---|---:|---:|---:|
| Músicos | 1.201 | 952 | 249 |
| Organistas | 320 | 326 | -6 |
| Músicos e organistas | 1.521 | 1.278 | 243 |
| Total geral do local | 2.440 | 2.092 | 348 |

A diferença de 348 não permite identificar automaticamente pessoas ausentes da lista. Há divergências por categoria e no próprio PDF: o indicador principal de organistas informa 320 e o gráfico informa 310. Os instrumentos somam 1.201, confirmando o total musical masculino declarado. O bloco apoio/irmandade soma 858. Músicos, organistas e esse bloco somam 2.379; restam 61 para o total geral, sem conciliação explícita no documento. O bloco de cargos soma 229 e pode sobrepor músicos e organistas, portanto não é uma parcela independente para fechar o total.

O projeto já contém o fechamento declarado de 2.440 em `docs/references/music_events/2026-05-17_itapevi_closing.json`. Esse valor é referência documental, não uma lista de 2.440 presenças nominais.

## Separação por município de origem

Aplicando a mesma agregação do painel aos registros de produção de maio, com todos os locais incluídos e origem limitada aos sete municípios da Regional:

| Origem | Músicos | Organistas | Ministério exclusivo | Apoio | Irmandade | Total |
|---|---:|---:|---:|---:|---:|---:|
| Itapevi | 304 | 123 | 15 | 21 | 212 | 675 |
| Jandira | 54 | 20 | 0 | 1 | 43 | 118 |
| Santana de Parnaíba | 70 | 12 | 3 | 1 | 20 | 106 |
| Cotia | 52 | 12 | 1 | 0 | 33 | 98 |
| Pirapora do Bom Jesus | 34 | 9 | 2 | 4 | 12 | 61 |
| Vargem Grande Paulista | 10 | 1 | 0 | 0 | 4 | 15 |
| Caucaia do Alto | 5 | 1 | 1 | 0 | 3 | 10 |
| Total da Regional | 529 | 178 | 22 | 27 | 327 | 1.083 |

Os demais 1.225 registros ficam fora desse recorte padrão de origem regional. Esse restante inclui origens externas e origens ainda não reconhecidas/corrigidas. Não se deve interpretar automaticamente todos como visitantes territorialmente validados.

Os 675 de origem Itapevi não são os 2.092 presentes no local Itapevi. São medidas distintas, calculadas sobre dimensões distintas.

## Imagem enviada

Reproduzi a agregação de setembro: 440 músicos, 108 organistas, 118 comuns, 52 encarregados e 816 presenças no recorte regional. Esses valores coincidem com a imagem. Portanto, os indicadores visíveis são de 20/09/2026, embora o seletor mostre 17/05/2026.

O código mantém o resultado anterior visível enquanto consulta o novo evento e também quando há erro de consulta. Isso permite a inconsistência visual observada. A imagem não permite determinar se foi capturada durante carregamento ou após uma falha. As respostas concorrentes já possuem controle de versão e cancelamento; a investigação não demonstrou mistura de registros de eventos no banco.

## Pendências de validação

1. **73 registros em Cotia:** para maio, a regra atual aceita destinos Itapevi e Pirapora. A importação atual rejeitaria esse arquivo enquanto esses destinos não fossem conferidos. Não transferir automaticamente os registros para outro local.
2. **Datas nominais diferentes:** 2.304 registros têm data original 17/05, três têm 16/05 e um tem 13/05. A importação preserva a data original em observação e atribui o evento à data confirmada. É necessário distinguir erro de data e registro antecipado legítimo.
3. **Possíveis duplicidades:** três ocorrências excedentes por nome normalizado/comum. São alertas, não duplicatas comprovadas. O importador deduplica por UUID, não por nome.
4. **Origem territorial:** há municípios em branco, grafias variantes e valores inválidos como `CLARINETE`. Fora do catálogo reconhecido, a agregação ainda pode separar grafias do mesmo município, como `SAO PAULO` e `SÃO PAULO`.
5. **Fechamento documental:** a diferença de 348 deve continuar explícita até conciliação com a fonte responsável. Não distribuir esse saldo entre municípios sem base nominal.

## Comportamento necessário para o fluxo pretendido

Após o envio da planilha global, a prévia deve mostrar total recebido, datas, locais, categorias, duplicidades e pendências territoriais. A confirmação deve preservar a fonte e registrar o que foi validado.

O painel deve apresentar três leituras identificadas:

1. **Público por local do ensaio, todas as origens:** total nominal e composição completa, incluindo visitantes.
2. **Participação por município/comum de origem:** músicos, organistas, ministério exclusivo, apoio, irmandade e total, com opções explícitas para Regional, visitantes e origem pendente.
3. **Conciliação com o fechamento declarado:** por exemplo, Itapevi em maio: declarado 2.440; nominal 2.092; diferença 348; situação pendente.

Os cards musicais podem permanecer, acompanhados de total geral visível e composição completa. Os cargos devem ser identificados como informação complementar sobreposta. Ao trocar o evento, o painel deve informar carregamento e impedir que indicadores antigos sejam atribuídos ao novo seletor; falhas devem manter explícita a data do último resultado carregado.

## Limites desta investigação

Não houve alteração de planilha, PDF, importações, presenças ou fechamento em produção. Foram verificadas contagens de banco e reproduzida a agregação. A classificação de cada pessoa, os 73 destinos Cotia, as possíveis duplicidades e a justificativa documental dos 348 ainda precisam de conciliação nominal. A leitura do PDF foi textual; não foi realizada auditoria gráfica do documento.
