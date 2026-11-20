# Justificativas dos eventos musicais

Formulário público: `/justificativas/`.
Painel autenticado: **Música → Justificativas**, `/musica/justificativas/`.

## Ativação

Aplicar `scripts/migrations/062_musica_justificativas_publicas.sql` no SQL Editor
do Supabase configurado para o projeto, depois das migrações 036 e 056.
A migração foi preparada para reaplicação. Não é uma migração do SQLite/Django.
As credenciais disponíveis nesta sessão não oferecem conexão SQL nem RPC de DDL.
A consulta inicial retornou HTTP 404; na revisão posterior, a tabela já estava
disponível no banco configurado, ainda sem envios públicos. Nenhuma migração
foi executada pelo agente no banco real.

O código pode ser revisado e testado localmente. Publicação não foi executada.
As justificativas anteriores são lidas das fontes já usadas pelos painéis de
ensaios, reuniões técnicas e acompanhamento, independentemente dos novos envios.

## Fluxo e identificação

O município filtra as comuns e os eventos futuros da agenda oficial. O primeiro
evento, ordenado por data e horário, vem selecionado; o usuário pode escolher
outro evento futuro aplicável. A terceira seleção identifica o evento; depois
o participante seleciona seu nome cadastrado na comum e informa o motivo.

A pesquisa inclui Encarregado Local, Encarregado Regional, Examinadora,
Secretário e Secretária da Música, Secretário e Secretária do GEM, Instrutor e
Instrutora. A grafia `SECRETÁRIO (A) DA MÚSICA` do SAM também é reconhecida.
O cargo real aparece abaixo do nome na sugestão e no registro do painel.
Cadastros inativos e nomes de outras comuns não são oferecidos.

SAM e irmandade usam a mesma conciliação de identidade do Acompanhamento.
Os cargos complementares de Secretaria e Instrução são preservados quando o
SAM registra outro cargo principal para a mesma pessoa. Duplicidades SAM e
irmandade são conciliadas por identidade concordante, preservando os aliases.
Não são alteradas permissões de acesso às pastas do sistema.

A fonte é a mesma configuração `MUSIC_AGENDA_CSV_URL` usada pelos exames. São
aceitos ensaios regionais, reuniões técnicas/ensaios por família (Cordas,
Madeiras e Metais), e reuniões musicais/do ministério. Não são incluídos
ensaios locais, exames, capacitações ou compromissos de outros departamentos.
Os aliases Vargem Grande, Fazendinha e Caucaia são conciliados com os sete
municípios administrativos do cadastro. Títulos sem abrangência reconhecida
não são oferecidos indiscriminadamente a todos os municípios.

O painel usa os mesmos componentes de `music-management.css` e o mesmo cabeçalho
e escopo de Exames e Testes. Os filtros são evento, município e comum; não há
busca separada por encarregado nem intervalo de datas redundante. Há quatro
indicadores com gráficos por administração e quadro dos agrupamentos municipais,
além de exportações PDF e Excel
com o mesmo recorte autorizado. A geração usa somente o carregamento do botão,
sem modal ou sobreposição de progresso. Os relatórios seguem
`docs/REPORT_EXPORT_STANDARD.md` e os geradores Python já usados pelo projeto.

O recebimento termina à meia-noite seguinte à data do evento em
`America/Sao_Paulo`. A API e um trigger PostgreSQL verificam o prazo. O
participante é novamente validado no cadastro ativo ao salvar; o navegador
envia um token assinado, não dados cadastrais livres. Há proteção CSRF,
limitação de requisições e unicidade por evento da agenda e identidade
normalizada da pessoa/comum. O motivo fica restrito ao painel autorizado.

A tabela guarda a identidade da agenda e uma cópia da data, título, horário,
tipo, família, abrangência, comum, nome e motivo recebidos. Esses dados são
imutáveis. Vínculos manuais possuem autoria e histórico de alterações.

## Integração dos painéis

O painel reúne os envios públicos e os registros existentes em
`musica_evento_encarregados` e `musica_ministerio_participacoes`. A expansão das
justificativas agrupadas reutiliza `individual_items`, a mesma função da lista
de justificativas dos ensaios. As versões de importação seguem
`_latest_event_versions`, como no painel original; cópias da mesma pessoa,
comum e evento entre fontes são contadas uma única vez.

A revisão de 20/11/2026 confirmou 18 justificativas individuais no ensaio de
15/11/2026. A agenda oficial contém `Reunião Geral da Música (Itapevi)` em
28/11/2026 às 09:00; esse título é reconhecido como reunião do ministério e,
por ser geral da Regional, fica disponível aos sete municípios. Não há data
ou título de reunião fixado no formulário: a origem continua sendo a agenda.

Ensaios e reuniões técnicas alimentam a conferência individual dos Encarregados
Locais, incluindo a coluna **Justificou**, somente quando a pessoa possui esse
cargo. Os demais cargos também aparecem em Justificativas e no Acompanhamento
individual por cargo. O vínculo persistido `person_key` identifica a pessoa no
cadastro; as transições SAM datadas são consultadas para recuperar a vigência
do cargo na data do evento. Cargos não identificados ficam a conferir e nunca
são presumidos como Encarregado Local. Não são criadas presenças nominais nem somadas justificativas
ao público físico. Presença já conferida prevalece, preservando a justificativa
original. Aliases da mesma pessoa no SAM e na irmandade são conciliados.

A associação automática exige um único evento compatível no conjunto completo
da data: tipo, família e sede/município também precisam corresponder. O vínculo
é persistido se o evento já existir no momento do envio. Se for importado
posteriormente, a justificativa passa a ser projetada no destino compatível.
Não é criada uma base SAM ou uma contagem fictícia para eventos futuros.

Sem destino ou com ambiguidade, o registro continua salvo e aparece como
**Aguardando vínculo** no painel novo. Após cadastrar/importar o evento, a
associação única é reconhecida automaticamente. Quando houver mais de um
destino compatível, a administração regional/global pode selecionar o correto.
Perfis restritos só consultam registros do próprio escopo. O botão **Ver painel**
abre o evento correspondente e seu ano.

## Referências de design

O CSS e o logotipo do formulário foram reutilizados de
`APP_EnR/src/screens/PublicMeetingScreen.tsx` e `src/img/logo-ccb-light.png`:
Inter/Outfit, cartão de 548 px, azul `#1e4b7a`, campos de 54 px e medidas
responsivas originais. Os campos Evento e Motivo foram acrescentados ao fluxo.
O painel usa os componentes compartilhados de `music-management.css` e a parcial
`music-management-scope.html`, os mesmos empregados em Exames e Testes.

## Verificação

```powershell
python manage.py check
python manage.py test ColorAdminApp.tests.tests_music_justification_portal ColorAdminApp.tests.tests_music_events_justifications ColorAdminApp.tests.tests_music_events_conductors ColorAdminApp.tests.tests_music_ministry --noinput
node --test ColorAdminApp/tests/music_justification_public_ui.test.cjs ColorAdminApp/tests/music_justifications_panel_ui.test.cjs
node scripts/validation/test_music_justifications_public_sql.mjs
```

O último comando usa a instalação de PGlite disponível em
`tmp/ministry-sql/node_modules`; não acessa produção. Os testes do formulário
usam JSDOM. A inspeção da agenda oficial foi somente de leitura. Não foi
realizado envio de justificativas fictícias ao banco real.

### Resultado da validação local

- 137 testes de backend passaram nas suítes de justificativas, eventos,
  encarregados e acompanhamento; o teste antigo do menu foi alinhado à
  permissão Música, independente de Musicalização.
- 4 testes novos de interface e 5 testes existentes de justificativas passaram.
- A migração foi executada duas vezes em PostgreSQL isolado, verificando prazo,
  unicidade, permissões, imutabilidade, vínculo incompatível e auditoria.
- Foram gerados relatórios fictícios: PDF de 3 páginas e planilha impressa pelo
  Excel em 5 páginas, com revisão das páginas renderizadas e sem cortes.
- A API local respondeu HTTP 200 com 183 comuns e 3 eventos futuros; todos os
  novos arquivos estáticos responderam HTTP 200. O formulário foi aberto no
  navegador externo padrão do Windows.
- Os scripts legados `scripts/test_music_events_loading.cjs` e
  `scripts/test_music_ministry_loading.cjs` apresentam falhas também quando
  executados com os arquivos originais de `HEAD`; seus simuladores não refletem
  o comportamento e os elementos atuais dos painéis. Essas falhas preexistentes
  não foram ocultadas nem tratadas como aprovação da interface completa.


### Origem e pesquisa de participantes

A pesquisa combina termos parciais e fica limitada ao município e à comum selecionados. A seleção do nome não altera a comum. O servidor rejeita pessoas de outra comum, divergência entre município e comum, e novos cadastros manuais.

Eventos municipais aceitam apenas membros dos municípios abrangidos. Ensaios regionais e encontros explicitamente regionais ficam disponíveis a todos os municípios abrangidos, preservando a origem de cada participante. Mantém-se a janela de dois eventos abertos e um terceiro bloqueado.


Ensaios técnicos por família da agenda são conciliados por data, tipo, família e sede. Na ausência de evento correspondente, a integração cria um rascunho com sede e identidade determinística, sem base SAM presumida nem presenças. A justificativa pode ser vinculada ao rascunho; a abertura da conferência continua sujeita à validação existente do banco. As etapas podem ser repetidas sem duplicar o evento ou sede.
