# Recuperação no SAM — turmas, matrículas e históricos verificados

## Situação atual — recuperação concluída em 08/10/2026

As três turmas de 2026 da Vila das Chácaras / Itapevi estão recuperadas no SAM: Grupo 01 (64164, 3 matrículas), Grupo 02 (64163, 12 matrículas) e Grupo 03 — Ensaio do GEM (64165, 19 matrículas), envolvendo 19 alunos distintos. As 26 aulas preservadas e suas 288 chamadas foram conferidas, com 71 presenças e 217 ausências. Foram criadas 19 aulas adicionais; as sete aulas históricas do piloto foram reaproveitadas. A aula 466573 de 08/10/2026, que já existia fora do acervo histórico, foi mantida.

Todos os **353 lançamentos preservados** foram reconciliados por aluno, categoria, campos pedagógicos, data, multiplicidade, observação e autoria: 251 MSA, 13 métodos, 50 hinos e 39 escalas. A consulta final encontrou **zero registros ausentes e zero divergências de observação/autoria**. Não havia provas ou atividades no backup desses alunos; não foram inventadas.

Nesta ampliação foram recuperados 44 MSA ausentes nas fichas. Mais seis vínculos de MSA de Daniel Mendes foram reconstituídos pelas presenças preservadas nas aulas e pelos conteúdos em grupo comprovados nas fichas dos colegas: Daniel não tinha histórico MSA capturado no backup. Esses seis vínculos têm proveniência distinta e estão registrados como reconstrução por chamada + conteúdo de grupo. Houve **50 acréscimos de MSA nas fichas**, por **oito novos lançamentos em grupo** e reaproveitamento dos sete conteúdos do piloto. Nenhum MSA individual foi criado. A comparação completa confirmou que nenhuma linha anterior desapareceu e que Método, Hinário, Provas e Escalas permaneceram idênticos.

As quatro turmas finalizadas 51474, 51475, 51476 e 51483 não foram alteradas. O horário das aulas segue a configuração substituta aprovada, 09:30–11:00; a diferença para o término 11:30 de aulas antigas permanece documentada. O instrutor da aula de 28/03/2026 do Grupo 01 é Wilson de Oliveira Barbosa Junior, conforme fonte; as demais aulas usam Olício Francisco Machado. Datas históricas e conteúdos foram preservados, incluindo os três MSA distintos de 31/08/2026 e os intervalos registrados na fonte. Datas de cadastro no SAM representam a recuperação atual.

Comprovantes privados: `.backups/sam/all_histories_recovery_journal.json`, `.backups/sam/all_students_history_before.json`, `.backups/sam/all_students_history_after.json` e `.backups/sam/all_histories_final_reconciliation.json`. O diário mantém o mapeamento das 26 aulas antigas para novas, as chamadas, os oito envios MSA e as etapas reaproveitadas. A cópia fonte 35ab4ad5-bc45-4b15-bbb1-7fac09fb0247 teve a integridade criptográfica validada; não foi modificada.

A comparação após a recuperação produz zero candidatos ausentes no acervo desses 19 alunos. Isso evita um segundo envio dos registros recuperados. A restauração geral em lote pela interface continua indisponível; esta execução foi controlada e autorizada para as três turmas da Vila das Chácaras. Não representa recuperação de outras comuns nem de registros que não estavam preservados.

Os registros abaixo documentam as etapas anteriores do piloto; seus escopos e pendências são históricos, anteriores à conclusão acima.


Destino: BR-22-2999 — Vila das Chácaras, Itapevi.
Turma proposta: GRUPO 02 - 2026, identificador original SAM 59927.
Aluno: CRISTHOPHER LOPES DE AGUIAR, identificador SAM 501845.
Cópia de referência: 99edf49d-fd07-40b7-ac48-750d4c6f9d68.

No ensaio local: 7 presenças em 18 chamadas; 42 registros MSA, 6 método,
3 hinário e 8 escalas. Nenhuma prova ou atividade encontrada nessa cópia.
Esses totais são históricos individuais preservados, não quantidades autorizadas
para envio. O histórico pode abranger outras turmas; não atribuir automaticamente
os lançamentos à turma proposta.

## Escopo

Uma turma e a matrícula de um aluno já identificado no SAM. Não criar outro
cadastro de aluno. Não recriar as quatro turmas finalizadas. Não publicar todo o
histórico individual automaticamente, nem gerar provas ou atividades ausentes.

## Etapas necessárias antes da execução

1. Consultar o SAM atual, incluindo turmas finalizadas e todas as páginas, e
   comprovar a ausência da turma por identidade e conteúdo. Se existir, reutilizar.
2. Confirmar o aluno pelo identificador 501845 e comum; divergência bloqueia o piloto.
3. Ler completamente todas as categorias do histórico desse aluno no SAM e
   comparar IDs, campos e multiplicidade. Registros existentes são excluídos do envio;
   registros equivalentes com IDs diferentes exigem revisão; leitura incompleta não
   comprova ausência. Nenhum vínculo turma/aula pode ser inferido pela data.
4. Inspecionar e validar os formulários/operações reais de criação, campos
   obrigatórios, autoria e efeitos sobre o histórico. Lançar uma aula em grupo pode
   gerar registros automaticamente: conferir esse efeito antes de lançar históricos.
5. Produzir uma lista concreta apenas das ausências confirmadas com os vínculos
   corretos. Sem unicidade/idempotência e controle de concorrência no destino,
   manter a automação de envio bloqueada.
6. Reconsultar antes de cada operação e conferir o resultado após ela; registrar
   novos IDs. Resposta incerta exige consulta, nunca repetição automática.
7. Conferir no SAM a turma, matrícula e cada lançamento do piloto. Repetir a
   comparação deve produzir zero novas criações para os registros recuperados.
8. Aguardar a validação do usuário antes de ampliar o escopo.

## Situação

Primeiro envio autorizado pelo usuário e realizado em 08/10/2026: turma e matrícula do piloto. O envio dos lançamentos ainda não foi executado.
Não existe adaptador de escrita validado. O acesso alternativo pelo cliente de leitura existente autenticou com sucesso.
As operações de criação e a conferência final permanecem pendentes.

## Consulta realizada no SAM em 08/10/2026

- Listagem consultada explicitamente com `status=0` (incluir finalizadas), sem filtro
  textual: 1.472 linhas recebidas de 1.472 informadas como acessíveis pelo servidor.
  O total geral informado é 1.747; não assumir cobertura de dados fora das permissões
  da conta. As quatro turmas antigas da comum continuam na resposta com IDs
  51474, 51475, 51476 e 51483. O ID 59927 e a descrição GRUPO 02 - 2026 não
  apareceram nessa listagem. O código BR da comum precisa ser conferido no formulário.
- Histórico aberto pelo identificador 501845; a página apresentou o nome do aluno.
- Comparação preliminar dos campos pedagógicos, data e autorizante, considerando
  multiplicidade, encontrou correspondência para 6 métodos, 3 hinos e 8 escalas.
  Não reenviar esses conjuntos. Observações e identificadores por evento ainda
  exigem conferência antes de classificar formalmente cada registro.
- MSA: 42 no backup e 39 normalizados da leitura atual; 35 correspondências dos
  campos centrais e 7 candidatos a revisão no backup. Diferença de contagem não
  equivale à quantidade perdida; há registros atuais adicionais. Os candidatos
  são de 21/02, 07/03, 21/03, 28/03, 25/04, 09/05 e 30/05 de 2026.
- As tabelas do portal também contêm hinos e escalas em grupo que o conversor
  existente não normaliza integralmente. Não usar o total convertido como prova
  de completude do portal. Nenhum candidato está autorizado para envio automático.
- O formulário real de turma pede curso, descrição, igreja, dia da semana,
  datas, horários, responsáveis e modalidade. O cadastro preservado da turma piloto
  tem início, término e dia/horário nulos. Foi solicitada confirmação ao usuário;
  não usar os horários de aulas como configuração oficial sem confirmação.
- Nenhum formulário de gravação foi submetido. As capturas brutas e a comparação
  preliminar estão em `scratch/sam_pilot_current.json`,
  `scratch/sam_pilot_groups_all.json` e `scratch/sam_pilot_comparison.json`.
  São evidências locais privadas; não comprovam uma execução de recuperação.

## Conferência adicional de leitura

O formulário de criação lista Vila das Chácaras / Itapevi com ID de igreja 4446
e Teoria Musical com ID de curso 1. Esses IDs são do formulário atual do SAM,
não equivalem ao código BR nem ao identificador antigo da turma.

- MSA, tabela `datatable1`: 23 linhas capturadas; total 23, filtradas 23, busca ``.
- Método, tabela `datatable3`: 6 linhas capturadas; total 6, filtradas 6, busca ``.
- Provas, tabela `datatable2`: 1 linhas capturadas; total 0, filtradas 0, busca ``.
- Escalas, tabela `datatable4`: 8 linhas capturadas; total 8, filtradas 8, busca ``.

Tabelas sem DataTable não informam total. Sua completude requer conferir o
HTML/origem, e o envio permanece bloqueado.


## Configuração informada pelo usuário para o piloto

Conforme referência enviada: sábado, 09:30–11:00, responsável Olício Francisco
Machado, sem segundo responsável, Ensino Irmãos e ativo. Esses dados foram
informados pelo usuário; não foram recuperados do cadastro da turma 59927.
O usuário autorizou datas substitutas "fev25" e "nov27" caso ausentes. Falta
confirmar as datas completas, pois o formulário exige dia/mês/ano e não se deve
inventar o dia nem interpretar silenciosamente mês/ano como dia/mês.
A turma a recriar continua sendo GRUPO 02 - 2026; não duplicar PERIODO 2 do print.


## Atualização solicitada em 08/10/2026

O usuário corrigiu o período do piloto para fevereiro de 2026 a novembro de 2028,
aos sábados. Para preparar o formulário, usar o primeiro sábado de fevereiro
(07/02/2026) e o último sábado de novembro (25/11/2028), como convenção operacional
explícita, não como datas históricas recuperadas. Horário 09:30–11:00 e demais dados
conforme referência informada. Nenhuma data substituta será aplicada às outras
turmas: elas devem manter o cadastro real consultado no SAM.


## Primeiro envio real — 08/10/2026

- Turma criada: **GRUPO 02 - 2026**, novo ID SAM **64163**, igreja **4446** —
  Vila das Chácaras / Itapevi. Cadastro reaberto e todos os campos comparados
  com a proposta aprovada: 07/02/2026 a 25/11/2028, sábado, 09:30–11:00,
  responsável 499470 (Olício Francisco Machado), Ensino Irmãos e ativo.
- Aluno existente **501845 — Cristhopher Lopes de Aguiar** matriculado e conferido
  como uma única linha da turma. Nenhum cadastro novo de aluno foi criado.
- A turma foi enviada uma única vez. A consulta imediatamente posterior apresentou
  resposta inesperada. O envio não foi repetido: uma nova sessão confirmou a turma.
- Correção da leitura: `status=0` e `status=1` retornam conjuntos separados, de
  1.472 e 276 linhas, respectivamente, totalizando as 1.748 turmas informadas
  pelo servidor após o piloto. O número da pré-consulta anterior cobria só um
  conjunto. A rotina agora une ambos por ID e bloqueia divergências de contagem.
- O piloto é uma operação individual acompanhada, com registro local da tentativa
  e verificação após envio; não é um adaptador de restauração em lote. O sistema
  continua sem botão de envio automático. Não ampliar o escopo sem validação.
- Nenhum lançamento MSA/método/hinário/prova/escala/progresso foi enviado.
  Os sete candidatos de MSA não possuem ID de aula associado no registro individual
  preservado. Não relacionar à nova turma por nome ou coincidência de data.
- Evidências privadas: `.backups/sam/pilot_group_send.json` e
  `.backups/sam/pilot_enrollment_send.json`. IDs antigos permanecem intactos nos
  backups; o registro do piloto contém a correspondência 59927 → 64163.


## Verificação após envio

Matrícula criada: ID **366571**. O histórico foi reaberto pelo ID do aluno e
comparado com a leitura anterior por cabeçalhos, valores e multiplicidade de
cada linha: MSA, Método, Hinário, Provas e Escalas permaneceram idênticos.
Nenhum lançamento dessas categorias foi criado ou alterado pelo piloto.
Comprovante local: `.backups/sam/pilot_send_verification.json`.
Validação do usuário pendente: no SAM, procurar GRUPO 02 - 2026 da Vila das Chácaras
(ID 64163) e conferir a matrícula ativa de Cristhopher, instrumento Clarinete.


## Diagnóstico do diário vazio — 08/10/2026

Após a validação do usuário, foi consultada novamente a listagem de aulas pelo
nome GRUPO 02 - 2026, com conferência da quantidade filtrada. Não foram encontradas
aulas associadas à turma antiga 59927 ou à nova 64163. Nenhuma escrita realizada
nesta investigação.

O primeiro envio criou somente a entidade turma e a matrícula. Não executou as
etapas de reconstrução das 18 aulas, das chamadas ou dos lançamentos faltantes.
A abertura `/aulas/index/64163` oferece um formulário para criar uma aula nova;
ela não recupera automaticamente as datas históricas. O aluno possui histórico
individual anterior preservado, mas isso não cria o diário da nova turma.

O fluxo a validar é turma → aula histórica → chamada do aluno → lançamento
individual ou em grupo → conferência no diário e na ficha. Para um primeiro
lançamento, usar uma data de aula preservada, seus horários/instrutor reais e
presença comprovada; não salvar a data atual sugerida pelo formulário para fingir
uma recuperação histórica. Também não converter indiscriminadamente MSA em grupo
em registros individuais. Os sete candidatos MSA ainda exigem um vínculo inequívoco
ou uma reconciliação explícita de revisão. O piloto atual valida turma/matrícula,
mas não pode ser declarado uma restauração completa de histórico.

Comprovante de leitura: `.backups/sam/pilot_history_diagnosis.json`.


## Teste completo de uma aula — executado em 08/10/2026

Após autorização do usuário, foi reconstruída uma aula histórica na turma 64163:

- Aula antiga 429021 → nova aula **466574**, data **30/05/2026**.
- Instrutor **499470 — Olício Francisco Machado**, comprovado pelo nome/ID e
  cadastro atual. A turma continua sendo Vila das Chácaras / Itapevi.
- Presença de **501845 — Cristhopher Lopes de Aguiar** comprovada no backup e
  registrada uma vez no SAM. A rotina `aulas/frequencia/{aula}/{ids}` registra
  presença diretamente por GET; sua resposta de sucesso foi preservada e a
  frequência foi conferida após a operação. Não repetir esse GET como consulta.
- **Um MSA em grupo**, fase **4.7–5.1**, páginas **41–42**, lições **30–34**,
  clave **Sol**, observação “Repassar não estudaram só tiraram duvidas”. O marcador
  estrutural “MSA em Grupo” do espelho foi representado pelo modo grupo do formulário,
  sem repetir o marcador dentro da observação nem converter o registro em individual.
- Fonte do MSA: registro local 82262c5c-c549-40e8-8ef2-b99da8cc3dbe.
  O vínculo com esta aula é uma reconstrução do piloto por aluno identificado,
  comum, presença comprovada, data e marcador de grupo; não alegar que o backup
  preservou a chave estrangeira original do MSA para a aula.
- A comparação de todas as linhas antes/depois confirmou exatamente um acréscimo
  na segunda tabela MSA (aulas em grupo): 16 → 17. A tabela individual de MSA e
  Método, Hinário, Provas e Escalas permaneceram idênticos. O lançamento normalizado
  coincide com a data, fases, páginas, lições, clave e observação do registro fonte.
- A turma também possui a aula **466573 de 08/10/2026**. Ela foi mantida intacta;
  não é a aula histórica reconstruída, e não deve ser confundida com duplicação
  do registro de 30/05/2026.
- Horário do piloto **09:30–11:00**, herdado da configuração informada pelo usuário.
  O backup da aula antiga informa **09:30–11:30**. A diferença está registrada e deve
  ser considerada na validação: o formulário de edição da aula não oferece campos
  nomeados para mudar esses horários. O formulário ainda sugere a data atual;
  nunca enviá-lo sem preservar explicitamente 30/05/2026.
- Restam **6 candidatos MSA** e as demais aulas/chamadas para revisão posterior.
  Nada disso foi enviado nesta etapa. A automação de restauração em lote segue bloqueada.

### Como validar no SAM

Abrir Histórico de aulas, procurar GRUPO 02 - 2026 da Vila das Chácaras e selecionar
**30/05/2026** (ID 466574). Conferir a presença de Cristhopher e os detalhes MSA.
Na ficha do aluno, abrir **MSA → MSA - Aulas em grupo** e localizar a mesma data.
O lançamento não aparece como lição individual na tabela superior, porque o registro
fonte era em grupo. Não criar uma cópia individual só para fazê-lo aparecer ali.

Comprovante: `.backups/sam/pilot_complete_lesson_verification.json`.
Históricos antes/depois: `.backups/sam/pilot_one_lesson_history_before.json` e
`.backups/sam/pilot_one_lesson_history_after.json`. A nova aula e o MSA tiveram uma
única tentativa de envio; verificações posteriores foram somente de leitura.


## Continuação do aluno piloto — seis MSA recuperados em 08/10/2026

Após o usuário validar visualmente o primeiro MSA e autorizar a continuação, foram recuperadas as seis datas restantes de Cristhopher Lopes de Aguiar (SAM 501845), na turma GRUPO 02 - 2026 (64163), Vila das Chácaras / Itapevi (igreja 4446). Cada aula e presença foi comparada com o backup; cada envio teve uma única tentativa registrada, seguida de nova consulta ao histórico.

| Data histórica | Nova aula SAM | Resultado |
| --- | --- | --- |
| 2026-02-21 | 466582 | Presença e MSA em grupo conferidos |
| 2026-03-07 | 466583 | Presença e MSA em grupo conferidos |
| 2026-03-21 | 466584 | Presença e MSA em grupo conferidos |
| 2026-03-28 | 466585 | Presença e MSA em grupo conferidos |
| 2026-04-25 | 466587 | Presença e MSA em grupo conferidos |
| 2026-05-09 | 466588 | Presença e MSA em grupo conferidos |

A comparação completa antes/depois confirmou **exatamente seis acréscimos na tabela MSA em grupo: 17 → 23**. Nenhuma linha anterior desapareceu; MSA individual, Método, Hinário, Provas e Escalas permaneceram idênticos. Não foram criadas novas matrículas nesta etapa. Somando o primeiro teste de 30/05/2026, os sete candidatos MSA ausentes do aluno piloto foram recuperados. Isso não significa que todas as aulas ou todos os alunos da turma foram restaurados.

O horário segue a configuração aprovada para a nova turma, 09:30–11:00; a diferença para o horário 09:30–11:30 das aulas antigas permanece documentada. As quatro turmas finalizadas de 2025 não foram alteradas. A recuperação dos demais alunos/turmas exige definir o escopo e comparar seus registros atuais, considerando que um MSA em grupo pertence à aula e não deve ser reenviado para cada aluno.

Comprovantes: `.backups/sam/cristhopher_six_msa_recovery.json`, `.backups/sam/cristhopher_six_msa_before.json` e `.backups/sam/cristhopher_six_msa_after.json`.


## Ampliação autorizada — turmas e matrículas em 08/10/2026

Após validar os sete MSA do aluno piloto, o usuário autorizou incluir as outras turmas e alunos. Nesta etapa, foram recuperadas apenas as três turmas de 2026 da Vila das Chácaras / Itapevi (igreja SAM 4446) e suas matrículas ativas preservadas. Foram reutilizados os 19 cadastros de membros existentes; nenhum cadastro de aluno foi criado ou alterado.

| Turma | ID antigo | ID atual | Matrículas conferidas |
| --- | --- | --- | --- |
| GRUPO 01 - 2026 | 59926 | 64164 | 3 |
| GRUPO 02 - 2026 | 59927 | 64163 | 12 |
| GRUPO 03 - ENSAIO DO GEM - 2026 | 59928 | 64165 | 19 |

Foram criadas duas turmas e 33 matrículas adicionais. A turma 64163 e a matrícula de Cristhopher já existiam e foram reaproveitadas. São 34 vínculos em três turmas, correspondentes a 19 alunos distintos; a participação de um aluno em turmas diferentes é preservada.

As duas turmas novas usam a configuração substituta informada pelo usuário e validada no piloto: 07/02/2026 a 25/11/2028, sábados das 09:30 às 11:00, Teoria Musical, responsável Olício Francisco Machado (499470), sem segundo responsável, Ensino Irmãos, ativo. Isso não foi recuperado do cadastro histórico apagado; os campos originais de início/fim permanecem nulos no backup.

Cada matrícula foi resolvida pelo identificador numérico do membro e conferida no destino, incluindo nome, comum, instrumento quando preservado e estado ativo. O instrumento histórico de Daniel Mendes estava vazio; foi mantido o instrumento atual Tuba, sem alterar seu cadastro. As quatro turmas finalizadas 51474, 51475, 51476 e 51483 permaneceram intactas.

Depois da primeira criação de turma, a sessão do SAM devolveu HTML onde era esperada a listagem JSON. O comprovante registrou a tentativa e a execução parou. Uma nova sessão de leitura confirmou a turma criada, que foi reaproveitada sem reenviar a criação. Após a matrícula de Daniel, a verificação detectou o instrumento histórico ausente; a retomada consultou novamente e reaproveitou a matrícula existente, sem repetir o envio. Os registros anteriores de tentativa permanecem no comprovante.

Uma consulta independente final resolveu novamente as identidades e confirmou todas as 34 matrículas, sem candidatos ausentes: **repetir a mesma recuperação produziria zero novas inclusões**.

Não foram recuperadas outras aulas, chamadas ou lançamentos nesta ampliação. A reconstrução dos históricos dos demais alunos é uma etapa distinta: exige comparar os registros existentes e reconciliar lançamentos em grupo por aula, evitando reenviar o mesmo lançamento para cada aluno. Os sete MSA do piloto permanecem recuperados.

Comprovantes: `.backups/sam/remaining_groups_enrollments_send.json` e `.backups/sam/remaining_groups_enrollments_preflight.json`. Os IDs antigos e novos são um mapeamento de recuperação; não substituir os identificadores nas cópias preservadas.


## Múltiplos MSA na mesma aula — controle aplicado

Na aula 466771 de 31/08/2026 havia três conteúdos distintos comprovados no backup para os mesmos presentes. Após o primeiro envio, o formulário passou a retornar o identificador do MSA existente, pronto para edição. O controle interrompeu a execução antes do segundo POST. A retomada conferiu os campos desse MSA no formulário da aula e nas fichas de todos os presentes, então usou a operação de criação validada com `id` vazio, sem enviar o identificador existente. Após cada inclusão foi comprovado exatamente um acréscimo por aluno, mantendo todas as linhas anteriores. Não se inferiu o ID do lançamento a partir do HTML da ficha, pois essa tabela não o expõe.

Essa interrupção não resultou em reenvio nem edição do primeiro MSA. Os dois conteúdos seguintes foram incluídos separadamente, preservando fases, páginas, lições, clave e observações da fonte. Os comprovantes registram o identificador que foi preservado e os campos efetivamente enviados.


## Conferência das datas exibidas na abertura — 08/10/2026

Após o usuário observar 08/10/2026 no formulário de abertura, foram reconsultados os detalhes das 26 aulas recuperadas. Todas as datas gravadas coincidem com as datas originais do backup; nenhuma aula histórica precisou de edição.

O campo `dt_abertura` do formulário de nova aula sugere automaticamente 08/10/2026 nas três turmas. Essa sugestão não modifica as aulas já gravadas. Os botões de retorno atuais apontam para:

| Turma | Aula de retorno | Data efetiva |
| --- | --- | --- |
| Grupo 01 — 64164 | 466760 | 29/08/2026 |
| Grupo 02 — 64163 | 466573 | 08/10/2026 |
| Grupo 03 — 64165 | 466774 | 06/06/2026 |

A aula 466573 do Grupo 02 é a aula adicional que já existia antes da recuperação histórica e foi preservada. Não há data original no backup para substituir sua data. A aula histórica de 31/08/2026 do Grupo 02 é 466771 e permanece com 31/08/2026.

Comprovante da consulta: `.backups/sam/restored_class_dates_check.json`. A conferência realizou zero gravações no SAM.
