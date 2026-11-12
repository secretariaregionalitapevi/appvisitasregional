import os,sys,json
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
import requests
from django.conf import settings
from django.core.cache import cache
from ColorAdminApp.modules.access_control import service_headers
from ColorAdminApp.modules.music_events import _read
from ColorAdminApp.modules.music_ministry import _rpc
before=json.loads(Path('tmp/oseia-before.json').read_text(encoding='utf-8'))
target='sam:4a3a23b8-a665-4ac9-99db-f9af2667b3f8';oldkey='sam:3ae914f3-5941-45a4-acc9-b7cb00e1cc39'
name='Os\u00e9ia de Souza';actor={'usuario_id':'codex:correcao-confirmada','usuario_nome':'Codex - correcao solicitada pelo usuario'}
with requests.Session() as client:
 def write(method,table,params,payload):
  headers={**service_headers(),'Prefer':'return=representation'}
  response=client.request(method,settings.SUPABASE_URL+'/rest/v1/'+table,headers=headers,params=params,json=payload,timeout=25)
  response.raise_for_status();return response.json()
 def audit(event_id,prior,after):
  write('POST','musica_ministerio_auditoria',{}, {'event_id':event_id,'person_key':target,'operacao':'CORRIGIR_IDENTIDADE_CONFIRMADA','anterior':prior,'posterior':after,**actor})
 # Preflight checks prevent replacing subsequent manual changes.
 for row in before['registry']:
  now=_read('musica_acompanhamento_aluno',id='eq.'+row['id']);assert now==[row]
 for entry in before['entries']:
  assert _read('musica_ministerio_participacoes',person_key='eq.'+entry['person_key'],event_id='eq.'+entry['event_id'])==[entry]
 assert len(before['entries'])==1 and before['entries'][0]['situacao']=='SEM_REGISTRO'
 original=next(r for r in before['registry'] if 'sam:'+r['id']==target)
 saved=write('PATCH','musica_acompanhamento_aluno',{'id':'eq.'+original['id'],'nome_aluno':'eq.'+original['nome_aluno']},{'nome_aluno':name})
 assert len(saved)==1
 for entry in before['entries']:
  assert not _read('musica_ministerio_participacoes',person_key='eq.'+target,event_id='eq.'+entry['event_id'])
  copied={k:entry[k] for k in ['event_id','comum','municipio','roles','situacao','observacoes']}
  copied.update(person_key=target,nome=name,source={**entry.get('source',{}),'reconciled_from':oldkey,'identity_confirmed_by':'usuario'})
  added=write('POST','musica_ministerio_participacoes',{},copied);assert len(added)==1
  audit(entry['event_id'],{'registry':original,'entry':entry},{'registry_name':name,'canonical_entry':added[0]})
  _rpc('musica_ministerio_conferir',{'p_evento':entry['event_id'],'p_pessoa':oldkey,'p_situacao':'NAO_APLICA','p_observacoes':'Identidade duplicada conciliada por confirmacao do usuario. Presencas consolidadas em Oseia de Souza.','p_version':entry['version'],'p_usuario_id':actor['usuario_id'],'p_usuario_nome':actor['usuario_nome']})
  source={**entry.get('source',{}),'canonical_person_key':target,'canonical_name':name,'original_name':entry['nome'],'identity_confirmed_by':'usuario'}
  linked=write('PATCH','musica_ministerio_participacoes',{'event_id':'eq.'+entry['event_id'],'person_key':'eq.'+oldkey,'version':'eq.'+str(entry['version']+1)},{'source':source});assert len(linked)==1
  audit(entry['event_id'],entry,{'identity_link':linked[0]})
  write('PATCH','musica_ministerio_pessoas',{'person_key':'eq.'+oldkey},{'roles':[]})
  directory={'person_key':target,'nome':name,'comum':entry['comum'],'municipio':entry['municipio'],'roles':entry['roles']}
  existing=_read('musica_ministerio_pessoas',person_key='eq.'+target)
  if existing:write('PATCH','musica_ministerio_pessoas',{'person_key':'eq.'+target},directory)
  else:write('POST','musica_ministerio_pessoas',{},directory)
cache.delete('music-events:registry:v2');cache.delete('music-ministry:sources:v5:2026')
print('Name corrected and identities linked with audit; original attendance retained')
