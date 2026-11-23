# Agenda Regional Itapevi — implantação com n8n

## O que foi implementado

Acesso em `/musica/agenda-regional/`, pelo menu Música → Agenda Regional.
O sistema gerencia solicitações, reservas, pareceres, configuração e histórico.
O PostgreSQL serializa todas as mutações por `pg_advisory_xact_lock` em funções
transacionais. O n8n busca trabalhos pendentes e integra com o Google Calendar.
Nenhuma tabela de frequência ou evento musical existente é modificada.

## Conexão e eventos que já existem no Google

Informar os IDs não importa os eventos. Há dois fluxos independentes obrigatórios:

1. `agenda_regional.workflow.json`: cria/cancela e verifica conflitos de solicitações.
2. `agenda_sincronizacao.workflow.json`: lê os eventos existentes e atualiza o espelho
   mostrado no calendário, sem modificar nada no Google.

Para habilitar a leitura, aplicar a migração `066_agenda_leitura_google.sql` após 064
e 065. Importar e publicar o fluxo de sincronização, selecionar Google Calendar OAuth2
no nó **Ler eventos existentes** e Header Auth nos dois nós que chamam o sistema.
Os dois fluxos usam o mesmo `app_url` e o mesmo `Authorization: Bearer <token>`.

Se o sistema roda no computador e o n8n está numa VPS, `127.0.0.1` no n8n aponta
para a VPS. É necessário um endereço HTTPS do backend alcançável pelo n8n: uma API
publicada ou um túnel HTTPS para o Django local. O acesso local pelo navegador pode
continuar normalmente. Uma API publicada pode usar o mesmo Supabase do sistema local.
Não basta informar o endereço do próprio n8n como `app_url`.

O token precisa estar em `AGENDA_N8N_TOKEN` no ambiente do servidor que recebe as
chamadas. No desenvolvimento deste projeto, a variável pode ficar no `.env.local`;
reiniciar Django após defini-la. O valor fica somente no ambiente e na credencial
Header Auth do n8n; não é enviado para a tela, exportado no workflow ou registrado
em mensagens. Em um backend publicado, configurar também o ambiente dessa hospedagem.

Ao abrir um mês, o sistema solicita a leitura do período visível. O trabalhador
consulta uma agenda a cada dez segundos; sete agendas levam várias execuções.
A tela acompanha o resultado a cada quinze segundos enquanto há leituras pendentes.
Depois, atualiza a solicitação a cada cinco minutos com a página visível. Atualizar
manualmente pede outra leitura, limitada a uma solicitação por minuto por período.
O fluxo de leitura precisa estar publicado, mesmo que não haja novos agendamentos.

Eventos Google aparecem como **Cadastrado no Google** ou **Google · Disponível**.
São somente leitura no sistema e não recebem pareceres retroativos. Eventos de dia
inteiro usam início inclusivo e término exclusivo no fuso de São Paulo. Os eventos
criados pelo sistema são deduplicados pelo par Calendar ID/Event ID. Uma leitura
completa vazia remove do espelho os eventos excluídos; falhas conservam o último
resultado válido e aparecem no diagnóstico. O máximo é 3000 eventos/2 MiB por leitura.

O aviso da tela agora distingue IDs ainda não salvos, token ausente, migração de leitura
pendente e erros/andamento da consulta. `Integração configurada` não significa que o
Google já tenha sido consultado com sucesso.

As aprovações continuam em quatro administrações, com sete agendas Google:

| Administração | Agendas municipais independentes |
|---|---|
| Cotia / Caucaia / VGP | Cotia; Caucaia do Alto; Vargem Grande Paulista |
| Itapevi | Itapevi |
| Jandira | Jandira |
| Santana / Pirapora | Santana de Parnaíba; Pirapora do Bom Jesus |

O município escolhido determina o destino Google. A administração determina o
encarregado, os suplentes, o prazo e as aprovações. A separação municipal não libera
automaticamente sobreposições entre municípios da mesma administração.

| Situação | Tratamento |
|---|---|
| Sem conflito | Reserva no sistema; confirma somente depois do Google |
| Sobreposição na mesma administração | Bloqueia, inclusive se a primeira solicitação ainda estiver pendente |
| Sobreposição entre administrações | Parecer de cada administração envolvida |
| Todos os pareceres favoráveis | Autoriza integração |
| Impedimento de qualquer encarregado | Decisão final da equipe Regional designada |
| Prazo sem resposta | Encaminha à Regional; nunca aprova por silêncio |
| Regional aprova ou recusa | Exige justificativa e preserva autoria no histórico |
| Resultado Google incerto | Conserva reserva para conciliação; não cria novo protocolo |
| Cancelamento de confirmado | Libera somente após confirmar remoção no Google |

O prazo inicial é 48 horas, ajustável por administração entre 1 e 720 horas.
Um lembrete é enfileirado uma vez na metade do prazo.
O prazo é verificado a cada chamada do trabalhador n8n, mesmo sem trabalhos de
integração; portanto o workflow deve permanecer ativo.

Reservas anteriores têm prioridade. Uma nova solicitação conflitante precisa
obter autorização para coexistir com as anteriores, sem revogar a reserva mais
antiga. Horários adjacentes são permitidos (`[início, término)`).

## 1. Preparar o banco

Em instalação nova, aplicar `scripts/migrations/064_agenda_regional.sql` e depois
`scripts/migrations/065_agenda_calendarios_municipais.sql`, primeiro em homologação.
Aplicar também `scripts/migrations/066_agenda_leitura_google.sql` para o espelho de leitura.
Se a 064 já foi aplicada, executar somente a 065. Não repetir a 064.
Cada migração é de execução única, dentro de uma transação; não é um script de
limpeza/recriação. Faz referência à tabela `profiles` já existente.

A 065 preserva os eventos, pareceres, responsáveis e os destinos Google já vinculados.
Reaproveita os IDs inequívocos de Itapevi e Jandira. Os antigos IDs compartilhados
de Cotia/Caucaia/VGP e Santana/Pirapora ficam disponíveis para consulta na configuração;
nenhum município é escolhido automaticamente como dono desses IDs. Complete os sete
destinos antes de solicitar novos eventos. Eventos já vinculados conservam o destino
anterior para conciliação e cancelamento; não são movidos nem duplicados pela migração.

As tabelas usam RLS e não são acessíveis a `anon` nem `authenticated`. O backend
lê com `service_role` e escreve exclusivamente pelas RPCs `agenda_operar` e
`agenda_trabalho`. A chave Supabase nunca vai ao navegador nem ao n8n.

## 2. Configurar o sistema

No ambiente do servidor Django, definir `AGENDA_N8N_TOKEN` com segredo aleatório
de pelo menos 32 bytes. Reiniciar/republicar o servidor conforme sua hospedagem.
Não registrar esse valor em arquivos versionados ou mensagens.

Entrar como administrador global, abrir Agenda Regional → Configurar:

1. Informar os sete IDs Google Calendar, um por município (não URLs de compartilhamento).
2. Designar um encarregado titular por administração; suplentes são opcionais.
3. Designar os membros da equipe Regional que podem decidir a etapa final.

Configurar também as sete agendas Google com o fuso `America/Sao_Paulo`.

As administrações são Cotia/Caucaia/VGP, Itapevi, Jandira e Santana/Pirapora.
Não é possível reutilizar o mesmo Calendar ID em dois municípios. Trocar o
destino de uma agenda municipal já configurada com reservas ativas é bloqueado.
O prazo continua sendo salvo por administração, separadamente dos sete IDs.

Somente o administrador global configura vínculos. Ter nível regional não torna
alguém automaticamente autorizador: é necessário vínculo explícito com a equipe.
Qualquer membro designado da equipe Regional pode concluir a decisão final.

A pasta Música e o escopo territorial são conferidos pelo servidor. Um usuário
municipal solicita apenas no próprio município, exceto quando designado responsável
por uma administração. Aprovações seguem o vínculo explícito.
O acesso exclusivo Música destinado ao APP_CARTAS continua restrito pelo middleware;
esta implementação não amplia essa liberação para o dashboard ou esta agenda.

## 3. Importar o fluxo de Google Calendar

Importar `scripts/n8n/agenda_regional.workflow.json` no n8n. O arquivo é entregue
inativo e sem segredos. Não sobrescreve workflows existentes.
Se já importou a versão anterior para quatro agendas, importe este arquivo atualizado
e desative a versão antiga antes de publicar a nova. O protocolo 2 é obrigatório;
workflows antigos não podem reservar trabalho nem enviar resultados para esta versão.

1. No nó **Configurar aplicação**, substituir `app_url` pelo endereço HTTPS do
   sistema Django acessível ao n8n (não pelo endereço do próprio n8n).
2. Criar credencial **Header Auth** chamada `Agenda Regional API`:
   nome do header `Authorization`, valor `Bearer <AGENDA_N8N_TOKEN>`.
3. Selecionar essa credencial nos nós **Reservar trabalho** e **Registrar resultado**.
4. Criar credencial **Google Calendar OAuth2**, conectar a conta institucional e
   selecioná-la nos dez nós nativos Google Calendar e em **Conferir remoção após
   falha**, a única consulta HTTP excepcional ao Google.
5. A conta precisa ler as sete agendas e criar/excluir eventos nos destinos. Mantenha
   também acesso a agendas anteriores que ainda tenham eventos vinculados.
6. Configurar o fuso do workflow como `America/Sao_Paulo` e validar os caminhos
   de sucesso e erro em homologação antes de publicar.

O trabalhador busca uma solicitação por minuto. A reserva do trabalho expira em
dez minutos; uma nova execução usa outro token e invalida callbacks antigos.
Se houver demanda maior, aumentar a frequência após medir duração e limites.

O ID Google é o UUID do evento sem hífens, estável em todas as tentativas. Antes
de criar, o fluxo procura esse ID nas consultas de eventos; após uma falha ambígua,
reprocessar pela tela concilia o mesmo evento. O nó **Criar no Google** usa os campos
nativos de título, local, início, término e **Additional Fields → ID**. Uma resposta
perdida não deve gerar um novo cadastro.

As sete consultas são nós nativos **Event → Get Many**, uma para cada município:
Cotia, Caucaia do Alto, Vargem Grande Paulista, Itapevi, Jandira, Santana de Parnaíba
e Pirapora do Bom Jesus. **Conferir destino do evento** também consulta a agenda já
vinculada ao protocolo, permitindo conciliar registros anteriores à separação.
Cada nó usa **Return All**, **After**, **Before**,
expansão de recorrências e **Always Output Data**. Os nós Code seguintes consolidam
os vários eventos e preservam o caso de agenda vazia, sem esconder erros.

O cancelamento usa **Event → Delete**. Em sucesso, o nó nativo retorna `success:true`.
Se houver erro, **Conferir remoção após falha** faz GET autenticado para distinguir
evento já ausente (404/410) de falha de rede/permissão. Essa exceção permanece HTTP
porque o nó nativo, em Continue on Error, retorna somente a mensagem do erro. Um GET
200 de evento ainda existente nunca é interpretado como exclusão concluída.

O fluxo consulta ocorrências recorrentes nas sete agendas (`singleEvents=true`).
Compromissos de dia inteiro ocupam seu intervalo completo. Eventos marcados como
Disponível e cancelados não bloqueiam. Erro de permissão, rede ou paginação deixa
a integração em verificação, sem confirmar o horário.

O **Return All** dos nós nativos percorre as páginas do Google. Não há corte em
2.500 ocorrências. Uma falha durante a consulta impede a confirmação; não é tratada
como agenda livre.

Eventos internos já autorizados são reconhecidos por administração, ID, título,
local e intervalo. Alterações manuais no Google exigem conciliação. Um conflito
Google sem correspondência no sistema, em outra administração, vai à Regional,
pois ainda não tem solicitação interna nem pareceres vinculados. Conflito externo
na própria administração recusa a solicitação. A autorização externa considera
também o `etag`, exigindo nova decisão se o compromisso mudar.

Os usuários devem criar, cancelar e reorganizar eventos pelo sistema. Escritas
diretas no Google podem ocorrer entre consulta e criação e não participam da
transação PostgreSQL. Restrinja a edição direta para preservar a garantia de reserva.

## 4. Notificações opcionais

As pendências e pareceres já aparecem no sistema. Uma caixa de saída transacional
registra notificações para solicitante, responsáveis envolvidos e equipe Regional.

O workflow `scripts/n8n/agenda_notificacoes.workflow.json` entrega essa caixa de
saída a um **receptor de notificações a configurar**, sem presumir fornecedor de
WhatsApp ou e-mail. Não ativar antes de configurar o canal:

1. Informar `app_url` e `notification_url` no nó Configurar aplicação.
2. Selecionar `Agenda Regional API` nos dois nós Django.
3. Configurar a credencial Header Auth `Agenda Canal Notificações` do receptor.
4. O receptor deve aceitar o JSON, escolher o contato/canal e retornar 2xx somente
   após aceitar a entrega duravelmente. Deve deduplicar pelo header `Idempotency-Key`.

O payload contém tipo, destinatário aprovado com contatos cadastrados, resumo do
evento e link para análise. O receptor não recebe a credencial do sistema. Em falha,
o item volta a ficar disponível após dez minutos. Cada execução entrega um item.
Perfis sem aprovação não são enviados. Não há confirmação de entrega real sem
configurar e testar esse receptor. As ações de aprovação ocorrem sempre no sistema.

## APIs de integração

Todas usam POST JSON e `Authorization: Bearer <token>`. Cookies não autenticam.
As quatro rotas são isentas apenas de sessão/CSRF, e validam o token na própria API.

| Rota sob `/integracoes/agenda-regional/api/` | Entrada / saída |
|---|---|
| `buscar/` | `{"protocol_version":2}` → `{"job": null}` ou trabalho com reserva exclusiva |
| `resultado/` | `protocol_version:2`, `id`, `lease_token`, `resultado` e dados do Google |
| `notificacao/` | `{}` → `{"notification": null}` ou notificação reservada |
| `notificado/` | `id` e `lease_token`, somente após aceite do canal |
| `buscar_leitura/` | `{}` → `{"job":null}` ou uma leitura reservada do período |
| `resultado_leitura/` | `id`, `lease_token`, `resultado:ok/erro`, `eventos` completos |

Resultados aceitos: `confirmado` (exige `google_event_id` esperado), `cancelado`,
`conflito_externo` (lista de conflitos) e `erro`. O sistema deriva todas as decisões
de aprovação da sessão do usuário; o n8n não pode emitir parecer como uma pessoa.
Os conflitos identificam `administracao_id`, `agenda_id` municipal e `calendar_id`
Google. Uma autorização para um evento em Cotia não vale para o mesmo ID encontrado
em Caucaia. O trabalho expõe `calendar_schema: municipal-v1` e os sete destinos.

## Operação e limites desta versão

- Atualizar a tela para acompanhar integrações; pendências podem ser abertas pelo
  link `?evento=<uuid>` das notificações.
- Reprocessar integração é permitido à equipe Regional designada e ao global.
- A agenda aceita compromissos futuros com duração de até sete dias.
- Reagendamento nesta versão: cancelar, aguardar a remoção se confirmado e enviar
  uma nova solicitação. Nenhuma autorização antiga é transferida ao novo horário.
- Recorrências podem existir no Google e são consideradas nos conflitos; o cadastro
  de séries recorrentes pelo sistema não está incluído nesta versão.
- O vínculo com frequência de ensaios/RTs não é obrigatório nem criado automaticamente.
- Não há publicação ou aplicação automática desta migração no ambiente conectado.

## Validação reproduzível

```powershell
python manage.py check
python manage.py test ColorAdminApp.tests.tests_regional_agenda ColorAdminApp.tests.tests_module_access
node --test ColorAdminApp/tests/regional_agenda_worker.test.cjs
node --test ColorAdminApp/tests/regional_agenda_workflow.test.cjs
python scripts/n8n/build_agenda_workflow.py
```

Para executar os testes de PostgreSQL isolado (não acessam o Supabase):

```powershell
npm.cmd install --prefix tmp/agenda-validation --ignore-scripts --no-audit --no-fund @electric-sql/pglite
node --test scripts/validation/064_agenda_regional.test.cjs
node --test scripts/validation/065_agenda_calendarios_municipais.test.cjs
node --test scripts/validation/066_agenda_leitura_google.test.cjs
```

Para regenerar os arquivos importáveis após alterar a lógica do trabalhador, executar
`python scripts/n8n/build_agenda_workflow.py`. Os testes usam o mesmo código JavaScript
embutido nos nós Code do workflow.

Para testar os formulários e a navegação usando o template real, sem navegador ou rede:

```powershell
npm.cmd install --prefix tmp/agenda-validation --ignore-scripts --no-audit --no-fund jsdom
python scripts/validation/render_agenda_fixture.py
node --test ColorAdminApp/tests/regional_agenda_ui.test.cjs
```
