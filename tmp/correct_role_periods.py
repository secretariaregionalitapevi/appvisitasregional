import os,sys,json
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from ColorAdminApp.modules.music_events import _read
from ColorAdminApp.modules.music_ministry import _rpc
from ColorAdminApp.modules.access_control import service_headers
from django.conf import settings
import requests
s=json.loads(Path('tmp/pdfs/ministry-matrix/data.json').read_text(encoding='utf-8'))
hen=next(r for r in s['rows'] if r['key']=='sam:8539e275-8af6-444f-b119-95f8b4110635')
jef=next(r for r in s['rows'] if r['key']=='importado:754c9592-e765-5846-8881-72cb84168861')
keys=[hen['key'],jef['key']]
entries=_read('musica_ministerio_participacoes',person_key='in.('+','.join(keys)+')')
reviews=_read('musica_ministerio_legado_conferencias',person_key='in.('+','.join(keys)+')')
Path('tmp/role-periods-before.json').write_text(json.dumps({'entries':entries,'reviews':reviews,'people':[hen,jef]},ensure_ascii=False,indent=2),encoding='utf-8')
plan=[(hen,'2026-09-20','NAO_APLICA'),(hen,'2026-10-06','NAO_APLICA'),(jef,'2026-01-18','NAO_APLICA'),(jef,'2026-05-17','NAO_APLICA'),(jef,'2026-07-19','NAO_APLICA'),(jef,'2026-09-20','PRESENTE')]
actor={'p_usuario_id':'codex:correcao-confirmada','p_usuario_nome':'Codex - periodo do cargo confirmado pelo usuario'}
for person,day,state in plan:
 event=next(e for e in s['event_options'] if str(e['date'])==day)
 note=('Periodo confirmado pelo usuario: Henrique exerceu o cargo ate o evento de 19/07/2026. Jeferson passa a exercer depois desse evento. '+('Presenca de Jeferson em 20/09/2026 confirmada.' if state=='PRESENTE' else 'Nao exercia o cargo neste evento; nao se aplica.'))
 if event['id'].startswith('legado:'):
  event_id=event['id'].split(':',1)[1]
  old=[r for r in reviews if r['event_id']==event_id and r['person_key'] in person['aliases']];assert len(old)<=1
  result=_rpc('musica_ministerio_conferir_legado',{'p_evento':event_id,'p_pessoa':{'person_key':old[0]['person_key'] if old else person['key'],'nome':person['nome'],'comum':person['comum'],'municipio':person['municipio'],'roles':person['roles'],'situacao':state,'observacoes':note},'p_version':old[0]['version'] if old else 0,**actor})
 else:
  old=[r for r in entries if r['event_id']==event['id'] and r['person_key'] in person['aliases']];assert len(old)<=1
  if old:
   result=_rpc('musica_ministerio_conferir',{'p_evento':event['id'],'p_pessoa':old[0]['person_key'],'p_situacao':state,'p_observacoes':note,'p_version':old[0]['version'],**actor})
  else:
   payload={'event_id':event['id'],'person_key':person['key'],'nome':person['nome'],'comum':person['comum'],'municipio':person['municipio'],'roles':person['roles'],'situacao':state,'observacoes':note,'source':{'role_period_confirmed_by':'usuario','role_end_inclusive':'2026-07-19'}}
   response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_ministerio_participacoes',headers={**service_headers(),'Prefer':'return=representation'},json=payload,timeout=25);response.raise_for_status();result=response.json()[0]
   audit={'event_id':event['id'],'person_key':person['key'],'operacao':'CONFIRMAR_PERIODO_CARGO','anterior':None,'posterior':result,'usuario_id':actor['p_usuario_id'],'usuario_nome':actor['p_usuario_nome']}
   response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_ministerio_auditoria',headers=service_headers(),json=audit,timeout=25);response.raise_for_status()
 print(person['nome'],day,state,flush=True)
print('Role periods corrected with audit')
