import json
import sys
from pathlib import Path
import requests
from django.conf import settings
from ColorAdminApp.modules.music_events import _read, _reviews, _invalidate_annual
from ColorAdminApp.modules.music_events_justifications import metadata, pack_metadata
from ColorAdminApp.modules.access_control import service_headers

assert len(sys.argv)>1 and sys.argv[-1] in {'ENFERMO','JUSTIFICOU'}, 'Informe a situação escolhida pelo usuário.'
status=sys.argv[-1]
event_id='0c00b334-0ab6-4175-b759-028aef44161f'
rows=_read('musica_evento_encarregados',evento_id='eq.'+event_id,comum_chave='eq.BR-22-1252')
assert len(rows)==1
row=rows[0]
info=metadata(row['observacoes'])
assert {p['nome'] for p in info['pessoas']}=={'JORGE AMÂNCIO','OTONIEL LUIZ'}
Path('tmp/isaura-justifications-before-health-classification.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
for person in info['pessoas']:
    person.setdefault('motivo_original',person['motivo'])
    person['motivo']='Enfermidade'
    person['situacao']=status
    person['classificacao_confirmada_pelo_usuario']=True
info['motivo']='JORGE AMÂNCIO: Enfermidade | OTONIEL LUIZ: Enfermidade'
payload={'situacao':status,'local_id':None,'observacoes':pack_metadata(info),
         'updated_by_user_id':'codex:classificacao-solicitada',
         'updated_by_name':'Codex - classificação solicitada pelo usuário'}
response=requests.patch(settings.SUPABASE_URL+'/rest/v1/musica_evento_encarregados',
                        headers=service_headers('return=representation'),params={'id':'eq.'+row['id']},json=payload,timeout=20)
response.raise_for_status()
assert len(response.json())==1
_invalidate_annual()
saved,_=_reviews([{'id':event_id}])
isaura=[p for p in saved if p['comum_chave']=='BR-22-1252']
assert len(isaura)==2 and all(p['situacao']==status and p['observacoes']=='Enfermidade' for p in isaura)
print(json.dumps([(p['encarregado_nome'],p['situacao'],p['observacoes']) for p in isaura],ensure_ascii=True))
