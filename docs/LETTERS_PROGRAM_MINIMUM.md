# Programa Mínimo nas cartas de exames

A consulta é informativa. Nenhuma pendência pedagógica, falta de histórico ou indisponibilidade da consulta bloqueia a emissão.

## Abrangência

- Somente cartas de músicos nas modalidades Culto Oficial e Oficialização.
- Organistas e trocas de instrumento ficam fora da avaliação e dos percentuais.
- A etapa avaliada é a modalidade da carta, independentemente do nível atual do aluno.
- O vínculo é feito pelo `payload.pessoa_id`, correspondente ao ID do cadastro GEM. Não há aproximação por nome.

## Origem das regras

O painel usa `sam_program.assess_program(..., target=modalidade)`, preservando o comportamento padrão do GEM quando `target` não é informado. MSA, Método e Hinário são consultados nas tabelas de acompanhamento já utilizadas no GEM.

No APP_CARTAS, `src/program.js` e `src/program-rules.json` reproduzem essas regras para o servidor Node. As fixtures em `tests/fixtures/program-assessment.json` cobrem 42 avaliações de comparação com o Python. Ao alterar regras pedagógicas no GEM, atualizar a versão Node e as fixtures conjuntamente.

## Apresentação e histórico

O APP_CARTAS consulta ao selecionar o candidato ou alterar a modalidade e mostra o resultado abaixo do resumo. A consulta é refeita no servidor na emissão e salva em `cartas_emissoes.payload.program_assessment`, sem mudança de schema. O conteúdo da carta PDF permanece no modelo institucional existente.

A relação regional mostra a **consulta atual** ao GEM abaixo do nome, com os três boxes completos de MSA, Método e Hinário, copiados do resumo técnico do GEM (Exigido e Documentado). Ela não apresenta a consulta atual como se fosse a situação histórica na emissão. Cartas antigas sem vínculo aparecem como sem vínculo, sem presumir descumprimento.

## Estatística e exportação

O painel, o PDF e o Excel usam os filtros gerais da página e os filtros de município/comum da seção Cartas preenchidas. Cada aluno conta uma vez por modalidade, mesmo quando há mais de uma carta para exames distintos.

O indicador principal é `(requisitos pendentes + validação pendente) / alunos-etapas avaliados`, com o rótulo **sem comprovação completa**. Os dois grupos aparecem separadamente. Sem histórico, sem vínculo e consulta indisponível não entram no denominador. Na ausência de base, mostrar “Sem base avaliada”, nunca zero por cento.

PDF e Excel seguem `REPORT_EXPORT_STANDARD.md`, com identificação institucional, filtros, responsável, emissão, congelamento, filtro automático, largura de impressão ajustada e cabeçalho repetido. A exportação respeita o escopo de acesso do painel.

## Pendência por inatividade do músico

Cartas de músicos também consultam `sam_mirror_student_status`, a mesma origem operacional do GEM. Mais de 180 dias sem atividade sinaliza **INATIVO**; mais de 365 dias (`requires_review`) sinaliza **EXCLUIR**, como indicação de revisão, sem exclusão automática. Um cadastro explicitamente INATIVO ou EXCLUIR também gera o alerta. Essa consulta vale inclusive para cartas de troca de instrumento; organistas permanecem fora desta regra.

A emissão continua permitida. Na identificação e na revisão da carta aparece o alerta, com o último lançamento e a necessidade de ciência do ancião da música, do encarregado regional que atende e do secretário da regional. O servidor refaz a consulta na emissão e grava `payload.student_activity` e `payload.activity_review` junto à carta. A pendência interna é independente do resultado do exame (`review_result`) e não altera aprovação, reprovação ou contagens.

O painel principal destaca as pendências em uma seção de alertas internos, respeitando o escopo de acesso das cartas. PDF e Excel registram a situação, o último lançamento, a pendência e os responsáveis por ciência. Cartas antigas sem snapshot usam uma consulta atual identificada como tal; os dados da emissão não são inventados ou sobrescritos.

Nesta etapa, a comunicação é **somente interna**, conforme orientação do usuário. Não há disparo de WhatsApp ou chamada ao n8n. O fluxo externo ficou para uma etapa posterior.

## Verificação

```powershell
python manage.py test ColorAdminApp.tests.tests_music_letters_program ColorAdminApp.tests.tests_music_letters ColorAdminApp.tests.tests_sam_program --noinput
python manage.py check
# No APP_CARTAS:
node --test
```


## Rela??o de candidatos e entrega das cartas (06/11/2026)

O bot?o **Exportar / importar**, junto a Limpar na lista, abre o painel de rela??o para Regionais e Examinadoras. O filtro de pend?ncias GEM/SAM sempre inicia desligado. A rela??o PDF segue as colunas do modelo fornecido: n?mero, nome, comum, instrumento, observa??o e checkbox de carta entregue, com grupos por evento, tipo e modalidade e totais de inscri??es/entregues/faltantes. Preserva o cabe?alho institucional definido em `REPORT_EXPORT_STANDARD.md`.

A se??o **Controle de entrega das cartas** distingue inscri??o manual, emiss?o do PDF e recebimento efetivo. Emitir n?o marca a carta como entregue. Os registros manuais e as cartas emitidas s?o conciliados por evento + tipo + modalidade + nome normalizado + c?digo da comum, sem duplicar a inscri??o. A consulta tem pagina??o de 25 candidatos.

O prazo ? configurado por evento pela administra??o regional/global. A data da pr?-avalia??o ? expl?cita; o exame pode ocorrer posteriormente. O bot?o Sugerir sexta-feira usa a sexta-feira em ou antes de um m?s-calend?rio antes da pr?-avalia??o, incluindo ajustes para meses menores e virada do ano. A sugest?o ? edit?vel. O recebimento no pr?prio dia-limite ? pontual; sem recebimento, o prazo s? vence no dia seguinte. A compara??o usa datas locais de S?o Paulo.

Os estados s?o: aguardando, n?o entregue com prazo vencido, entregue no prazo, entregue em atraso, entregue sem prazo e entregue sem data informada. Nunca inferir pontualidade de uma entrega sem data ou de um evento sem prazo. O registro manual solicita a data efetiva; desfazer a marca??o ? auditado. Alterar o prazo recalcula os estados, preservando os recebimentos e a auditoria anterior.

A importa??o aceita XLSX/CSV, at? 5 MB e 1.000 candidatos. O modelo Excel inclui valida??es de tipo/modalidade/entrega, datas tipadas e filtros. O v?nculo SAM requer nome + c?digo da comum + tipo, com resultado ?nico (ID SAM opcional precisa confirmar essa mesma identidade). N?o h? associa??o aproximada por nome. A pr?via consulta as ?reas documentais pelo mesmo avaliador do GEM para m?sicos em Culto Oficial/Oficializa??o. Sem v?nculo ?nico, a rela??o pode ser importada, conservando a indica??o para revis?o. A importa??o n?o emite carta nem aprova candidato.

Uma pr?via assinada, vinculada ao usu?rio e v?lida por 20 minutos precede a confirma??o. Candidatos j? existentes s?o preservados, inclusive a entrega; corre??es s?o feitas no controle de entrega. Duplicados no pr?prio arquivo s?o rejeitados. N?o se importam f?rmulas nem arquivos descompactados com mais de 30 MB. Campos textuais exportados nunca s?o interpretados como f?rmulas.

### Banco de dados

Aplicar `scripts/migrations/044_cartas_relacao_entregas.sql` no mesmo Supabase das cartas. A migra??o cria as tabelas `cartas_relacao_candidatos`, `cartas_entrega_prazos`, `cartas_entrega_auditoria` e RPCs transacionais de recebimento, prazo e importa??o. RLS bloqueia anon/authenticated; apenas service_role acessa as tabelas, sempre ap?s a autoriza??o territorial no servidor. Os registros t?m respons?vel, hor?rio e vers?o para evitar sobrescrita concorrente. Nenhum recebimento ? convertido em aprova??o de exame.

Sem a migra??o, a se??o exibe um aviso expl?cito e continua permitindo consultar/exportar a rela??o derivada das cartas emitidas; grava??o e importa??o ficam indispon?veis. N?o h? altera??o autom?tica de estrutura no banco a partir do navegador.


### Prazo autom?tico pela pr?-avalia??o

A rela??o calcula o prazo antes de qualquer salvamento, inclusive em Todos os eventos. Um exame utiliza a pr?-avalia??o mais recente anterior ou no pr?prio dia, da mesma administra??o e do mesmo p?blico (m?sicos/organistas); a pr?pria pr?-avalia??o usa sua data. Nunca substituir uma pr?-avalia??o ausente pela data do exame. As op??es de refer?ncia s?o fornecidas pela agenda, e o v?nculo e a data aparecem junto do prazo.

O prazo padr?o ? a sexta-feira em ou antes de um m?s-calend?rio antes da pr?-avalia??o (ex.: pr?-avalia??o em 14/11/2026 gera 09/10/2026). Prazos salvos pelo respons?vel prevalecem sobre a sugest?o autom?tica. O bot?o Alterar na coluna Prazo abre a escolha de pr?-avalia??o e as datas edit?veis; salvar persiste a escolha com auditoria. Alterar a data de refer?ncia recalcula a sugest?o; ajustar a data-limite continua permitido. Edi??es ainda n?o salvas n?o s?o apagadas por atualiza??o autom?tica do painel.

O mesmo prazo efetivo alimenta os estados de entrega, indicadores e exporta??es. Se a agenda n?o identificar uma pr?-avalia??o correspondente, a interface informa isso e permite escolher uma data explicitamente. Nenhuma mudan?a adicional na migra??o 044 ? necess?ria.


### Fonte oficial e integridade das datas

O controle e os exames leem a mesma fonte CSV ao vivo incorporada no calendário oficial (`ccbagenda.vercel.app`), pelo Apps Script da agenda. A publicação antiga `docs.google.com/.../pub?output=csv` não é fallback permitido: ela continha eventos divergentes. Leitura UTF-8 explícita e cache identificado pela fonte, de até 60 segundos no controle de entregas.

Referências de pré-avaliação são obtidas somente dessa fonte, com administração e público correspondentes. Snapshots de cartas/relações não podem introduzir referências na agenda. A data de pré-avaliação é somente leitura e o servidor valida o ID oficial e sua data; apenas o prazo de entrega é editável. Prazos salvos cuja referência não exista mais na fonte oficial não prevalecem sobre a agenda atual. Na indisponibilidade da agenda, não estimar nem usar datas de snapshots.

Conferência real da fonte em 06/11/2026: músicos de Itapevi têm pré-avaliação em 14/11/2026 e avaliação em 28/11/2026. A sugestão de entrega é 09/10/2026; não há pré-avaliação de músicos em Itapevi em 21/11/2026 nessa fonte.
