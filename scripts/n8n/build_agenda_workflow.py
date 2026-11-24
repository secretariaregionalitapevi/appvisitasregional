"""Gera o workflow importável. Não acessa contas nem publica fluxos."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ColorAdminApp.modules.regional_agenda_catalog import CALENDARS

HERE = Path(__file__).resolve().parent
LOGIC = (HERE / 'agenda_worker_logic.js').read_text(encoding='utf-8').split("if(typeof module")[0]
JOB = "$('Reservar trabalho').first().json.job"
BASE = r"$('Configurar aplicação').first().json.app_url.replace(/\/$/,'')"
nodes, connections = [], {}


def node(name, kind, parameters, x, y, version=1, **extras):
    nodes.append({'id': name, 'name': name, 'type': 'n8n-nodes-base.' + kind,
                  'typeVersion': version, 'position': [x, y], 'parameters': parameters, **extras})


def connect(source, target, branch=0):
    outputs = connections.setdefault(source, {'main': []})['main']
    while len(outputs) <= branch:
        outputs.append([])
    outputs[branch].append({'node': target, 'type': 'main', 'index': 0})


def http(name, method, url, x, y, body=None):
    params = {'method': method, 'url': url, 'authentication': 'genericCredentialType',
              'genericAuthType': 'httpHeaderAuth', 'options': {'timeout': 45000}}
    credentials = {'httpHeaderAuth': {'id': '', 'name': 'Agenda Regional API'}}
    if body is not None:
        params.update({'sendBody': True, 'specifyBody': 'json', 'jsonBody': body})
    node(name, 'httpRequest', params, x, y, 4.2, credentials=credentials)


def calendar(name, operation, parameters, x, y):
    node(name, 'googleCalendar', {'resource': 'event', 'operation': operation, **parameters}, x, y, 1.3,
         credentials={'googleCalendarOAuth2Api': {'id': '', 'name': 'Google Agenda Regional'}},
         alwaysOutputData=True, onError='continueRegularOutput')


def locator(expression):
    return {'__rl': True, 'mode': 'id', 'value': '={{ ' + expression + ' }}'}


def condition(name, expression, value, x, y):
    node(name, 'if', {'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
        'conditions': [{'id': name, 'leftValue': expression, 'rightValue': value,
                        'operator': {'type': 'string', 'operation': 'equals'}}], 'combinator': 'and'}, 'options': {}}, x, y, 2.2)


def code(name, source, x, y, logic=True):
    node(name, 'code', {'jsCode': (LOGIC if logic else '') + '\n' + source}, x, y, 2)


node('Solicitação do sistema', 'webhook', {'httpMethod':'POST','path':'agenda-regional-processar','authentication':'headerAuth','responseMode':'lastNode','options':{}}, 0, 0, 2,
     webhookId='agenda-regional-processar',credentials={'httpHeaderAuth':{'id':'','name':'Agenda Regional API'}})
node('Configurar aplicação', 'set', {'assignments': {'assignments': [
    {'id': 'app_url', 'name': 'app_url', 'type': 'string', 'value': 'https://SEU-SISTEMA.example'}]}, 'options': {}}, 220, 0, 3.4)
http('Reservar trabalho', 'POST', '={{ ' + BASE + " + '/integracoes/agenda-regional/api/buscar/' }}", 440, 0, '{"protocol_version":2}')
condition('Há trabalho?', "={{ $json.job ? 'sim' : 'nao' }}", 'sim', 660, 0)
condition('É cancelamento?', '={{ $json.job.status }}', 'CANCELANDO', 880, 0)
calendar('Remover do Google', 'delete', {'calendar': locator(JOB+'.google_calendar_id'),
    'eventId': '={{ '+JOB+'.google_id }}', 'options': {}}, 1100, -300)
condition('Remoção confirmada?', "={{ $json.success === true ? 'sim' : 'nao' }}", 'sim', 1320, -300)
code('Resultado do cancelamento', f"return [{{json:agendaResult({JOB},'cancelado')}}];", 1540, -440)
# O nó nativo devolve apenas error.message. Somente após falha de exclusão,
# consultar o status HTTP diferencia evento ausente de falha de permissão/rede.
event_url = "'https://www.googleapis.com/calendar/v3/calendars/' + encodeURIComponent(" + JOB + ".google_calendar_id) + '/events/' + " + JOB + '.google_id'
node('Conferir remoção após falha', 'httpRequest', {'method':'GET','url':'={{ '+event_url+' }}',
    'authentication':'predefinedCredentialType','nodeCredentialType':'googleCalendarOAuth2Api',
    'options':{'timeout':45000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'json'}}}},
    1540,-180,4.2,credentials={'googleCalendarOAuth2Api':{'id':'','name':'Google Agenda Regional'}},
    onError='continueRegularOutput')
code('Conciliar cancelamento', f'return [{{json:agendaDeleted({JOB},$input.first().json)}}];',1760,-180)

calendar('Conferir destino do evento', 'getAll', {'calendar':locator(JOB+'.google_calendar_id'),
    'returnAll':True,'timeMin':'={{ '+JOB+'.inicio }}','timeMax':'={{ '+JOB+'.fim }}',
    'options':{'recurringEventHandling':'expand','showDeleted':False,
               'timeZone':{'__rl':True,'mode':'id','value':'America/Sao_Paulo'}}},1100,180)
code('Resultado destino', 'return [{json:agendaNativeList($input.all().map(i=>i.json))}];',1320,180)
connect('Conferir destino do evento','Resultado destino')
queries = [(c['id'],c['nome']) for c in CALENDARS]
previous = 'Resultado destino'
for index, (identity, label) in enumerate(queries):
    query, result = 'Consultar '+label, 'Resultado '+identity
    x = 1540 + index * 440
    calendar(query, 'getAll', {'calendar': locator(JOB+f".calendars.find(c=>c.id==='{identity}').calendar_id"),
        'returnAll': True, 'timeMin': '={{ '+JOB+'.inicio }}', 'timeMax': '={{ '+JOB+'.fim }}',
        'options': {'recurringEventHandling':'expand','showDeleted':False,
                    'timeZone': {'__rl':True,'mode':'id','value':'America/Sao_Paulo'}}}, x, 180)
    code(result, 'return [{json:agendaNativeList($input.all().map(i=>i.json))}];', x+220,180)
    connect(query,result)
    if previous:
        connect(previous,query)
    previous = result
sources = '['+','.join(JOB+f".calendars.find(c=>c.id==='{identity}')" for identity,_ in queries)+']'
responses = '['+','.join(f"$('Resultado {identity}').first().json" for identity,_ in queries)+']'
merge_source=f"const job={JOB}; const sources={sources}; const responses={responses};\n"+"if(!sources.some(c=>c&&c.calendar_id===job.google_calendar_id)){sources.push({id:'legado',administracao_id:job.administracao_id,municipio:job.municipio,calendar_id:job.google_calendar_id});responses.push($('Resultado destino').first().json);}\nreturn [{json:agendaConflicts(job,sources,responses)}];"
code('Consolidar conflitos',merge_source,4620,180)
condition('Pode criar?', '={{ $json.resultado }}', 'livre',4840,180)
calendar('Criar no Google', 'create', {'calendar':locator(JOB+'.google_calendar_id'),
    'start':'={{ '+JOB+'.inicio }}','end':'={{ '+JOB+'.fim }}','useDefaultReminders':True,
    'additionalFields': {'id':'={{ '+JOB+'.google_id }}','summary':'={{ '+JOB+'.titulo }}',
       'location':'={{ '+JOB+'.local }}','description':"={{ 'Agenda Regional Itapevi | Protocolo: ' + "+JOB+'.id }}',
       'showMeAs':'opaque'}},5060,60)
code('Resultado da criação', f'return [{{json:agendaNativeCreated({JOB},$input.first().json)}}];',5280,60)
http('Registrar resultado', 'POST', '={{ ' + BASE + " + '/integracoes/agenda-regional/api/resultado/' }}",5500,340,'={{ JSON.stringify($json) }}')
for a, b in [('Solicitação do sistema','Configurar aplicação'),('Configurar aplicação','Reservar trabalho'),('Reservar trabalho','Há trabalho?'),('Há trabalho?','É cancelamento?'),('É cancelamento?','Remover do Google'),('Remover do Google','Remoção confirmada?'),('Remoção confirmada?','Resultado do cancelamento'),('Resultado do cancelamento','Registrar resultado'),('Conferir remoção após falha','Conciliar cancelamento'),('Conciliar cancelamento','Registrar resultado'),(previous,'Consolidar conflitos'),('Consolidar conflitos','Pode criar?'),('Pode criar?','Criar no Google'),('Criar no Google','Resultado da criação'),('Resultado da criação','Registrar resultado')]:
    connect(a, b)
connect('É cancelamento?', 'Conferir destino do evento', 1)
connect('Remoção confirmada?', 'Conferir remoção após falha', 1)
connect('Pode criar?', 'Registrar resultado', 1)
node('Leia antes de ativar', 'stickyNote', {'content': '## Agenda Regional — sob demanda\n1. Configure app_url e credenciais.\n2. No webhook, selecione Header Auth usando o token compartilhado.\n3. Configure os nós Google.\n4. Publique e configure a URL de produção do webhook no servidor Django.\n5. Desative o fluxo antigo agendado.\n\nO sistema chama este fluxo quando há agendamento ou decisão. Consulte docs/AGENDA_REGIONAL_N8N.md.', 'height': 330, 'width': 440}, 0, -440)
workflow = {'name': 'Agenda Regional Itapevi — Google Calendar', 'nodes': nodes, 'connections': connections,
            'active': False, 'settings': {'executionOrder': 'v1', 'timezone': 'America/Sao_Paulo'},
            'pinData': {}, 'tags': []}
(HERE / 'agenda_regional.workflow.json').write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Workflow gerado, inativo e sem credenciais.')

# Canal opcional: o receptor decide se entrega por WhatsApp, e-mail ou outro meio.
# Não inclui credenciais nem presume um fornecedor contratado.
nodes, connections = [], {}
node('A cada minuto', 'scheduleTrigger', {'rule': {'interval': [{'field': 'minutes', 'minutesInterval': 1}]}}, 0, 0, 1.2)
node('Configurar aplicação', 'set', {'assignments': {'assignments': [
    {'id': 'app_url', 'name': 'app_url', 'type': 'string', 'value': 'https://SEU-SISTEMA.example'},
    {'id': 'notification_url', 'name': 'notification_url', 'type': 'string', 'value': 'https://SEU-CANAL.example/notificar'}]}, 'options': {}}, 220, 0, 3.4)
http('Buscar notificação', 'POST', '={{ '+BASE+" + '/integracoes/agenda-regional/api/notificacao/' }}", 440, 0, '{}')
condition('Há notificação?', "={{ $json.notification ? 'sim' : 'nao' }}", 'sim', 660, 0)
notification_body = "={{ JSON.stringify({...$json.notification,link:"+BASE+" + '/musica/agenda-regional/?evento=' + $json.notification.evento_id}) }}"
http('Entregar no canal', 'POST', "={{ $('Configurar aplicação').first().json.notification_url }}", 880, 0, notification_body)
delivery = nodes[-1]
delivery['credentials'] = {'httpHeaderAuth': {'id': '', 'name': 'Agenda Canal Notificações'}}
delivery['parameters']['options'] = {'timeout':45000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'text'}}}
delivery['parameters'].update({'sendHeaders':True,'headerParameters':{'parameters':[{'name':'Idempotency-Key','value':"={{ $('Buscar notificação').first().json.notification.id }}"}]}})
delivery['onError'] = 'continueRegularOutput'
condition('Entregue?', "={{ Number($json.statusCode)>=200 && Number($json.statusCode)<300 ? 'sim' : 'nao' }}", 'sim', 1100, 0)
http('Confirmar entrega', 'POST', '={{ '+BASE+" + '/integracoes/agenda-regional/api/notificado/' }}", 1320, 0,
     "={{ JSON.stringify({id:$('Buscar notificação').first().json.notification.id,lease_token:$('Buscar notificação').first().json.notification.lease_token}) }}")
for a,b in [('A cada minuto','Configurar aplicação'),('Configurar aplicação','Buscar notificação'),('Buscar notificação','Há notificação?'),('Há notificação?','Entregar no canal'),('Entregar no canal','Entregue?'),('Entregue?','Confirmar entrega')]:
    connect(a,b)
workflow = {'name':'Agenda Regional Itapevi — Notificações (canal a configurar)','nodes':nodes,'connections':connections,
            'active':False,'settings':{'executionOrder':'v1','timezone':'America/Sao_Paulo'},'pinData':{},'tags':[]}
(HERE / 'agenda_notificacoes.workflow.json').write_text(json.dumps(workflow,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Workflow opcional de notificações gerado, inativo e sem canal configurado.')

# Leitura independente: a visualização não depende de existir uma solicitação de agendamento.
nodes, connections = [], {}
node('Consulta do sistema', 'webhook', {'httpMethod':'POST','path':'agenda-regional-ler','authentication':'headerAuth','responseMode':'lastNode','options':{}},0,0,2,
     webhookId='agenda-regional-ler',credentials={'httpHeaderAuth':{'id':'','name':'Agenda Regional API'}})
node('Configurar aplicação', 'set', {'assignments': {'assignments': [
    {'id':'app_url','name':'app_url','type':'string','value':'https://SEU-SISTEMA.example'}]},'options':{}},220,0,3.4)
http('Reservar leitura','POST','={{ '+BASE+" + '/integracoes/agenda-regional/api/buscar_leitura/' }}",440,0,'{}')
condition('Há leitura?','={{ $json.job ? "sim" : "nao" }}','sim',660,0)
read_job="$('Reservar leitura').first().json.job"
calendar('Ler eventos existentes','getAll',{'calendar':locator(read_job+'.calendar_id'),
    'returnAll':True,'timeMin':'={{ '+read_job+'.inicio }}','timeMax':'={{ '+read_job+'.fim }}',
    'options':{'recurringEventHandling':'expand','showDeleted':False,
               'timeZone':{'__rl':True,'mode':'id','value':'America/Sao_Paulo'}}},880,0)
code('Preparar leitura completa',f'return [{{json:agendaSyncResult({read_job},$input.all().map(i=>i.json))}}];',1100,0)
http('Atualizar espelho no sistema','POST','={{ '+BASE+" + '/integracoes/agenda-regional/api/resultado_leitura/' }}",1320,0,'={{ JSON.stringify($json) }}')
for a,b in [('Consulta do sistema','Configurar aplicação'),('Configurar aplicação','Reservar leitura'),('Reservar leitura','Há leitura?'),('Há leitura?','Ler eventos existentes'),('Ler eventos existentes','Preparar leitura completa'),('Preparar leitura completa','Atualizar espelho no sistema')]:connect(a,b)
node('Leitura das agendas','stickyNote',{'content':'## Leitura sob demanda\n1. Aplique a migração 066.\n2. Configure app_url e as credenciais Header Auth e Google Calendar.\n3. Publique o fluxo e configure sua URL de produção no servidor Django.\n4. Desative o fluxo antigo de 10 segundos.\n\nO sistema chama o webhook somente ao solicitar atualização. Cada chamada processa uma agenda.','height':300,'width':440},0,-400)
workflow={'name':'Agenda Regional Itapevi — Sincronizar eventos existentes','nodes':nodes,'connections':connections,
          'active':False,'settings':{'executionOrder':'v1','timezone':'America/Sao_Paulo'},'pinData':{},'tags':[]}
(HERE/'agenda_sincronizacao.workflow.json').write_text(json.dumps(workflow,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Workflow de leitura do Google gerado, inativo e sem credenciais.')
