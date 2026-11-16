import json
import sys
from pathlib import Path
import requests
from django.conf import settings
from ColorAdminApp.modules.music_events import _read, _registry, _reviews, _invalidate_annual
from ColorAdminApp.modules.music_events_justifications import metadata, pack_metadata
from ColorAdminApp.modules.access_control import service_headers

event_id='0c00b334-0ab6-4175-b759-028aef44161f'
expected=[('IGOR ROMAO FERREIRA','BR-21-1563'),('WAGNER FABIANO PIRES','BR-22-3132')]
registry=_registry()
sites=_read('musica_evento_locais',evento_id='eq.'+event_id)
site=next(s for s in sites if s['nome']=='FAZENDINHA')
existing=_read('musica_evento_encarregados',evento_id='eq.'+event_id)
payloads=[]
for name,key in expected:
    people=[p for p in registry if p['nome_aluno']==name and p['comum_congregacao'].startswith(key+' - ')]
    assert len(people)==1
    person=people[0]
    current=[r for r in existing if r['comum_chave']==key]
    if current:
        assert len(current)==1
        r=current[0]
        assert (r.get('encarregado_nome') or metadata(r.get('observacoes')).get('nome'))==name
        assert r['situacao']=='PRESENTE' and r['local_id']==site['id']
        continue
    notes=pack_metadata({'nome':name,'motivo':'Presença confirmada expressamente pelo usuário a partir de mensagem encaminhada.',
                         'origem':'Confirmação de presença fornecida pelo usuário','cargo':'Encarregado Local',
                         'tipo':'confirmacao_administrativa_presenca','data_evento':'15/11/2026'})
    payloads.append({'evento_id':event_id,'comum_chave':key,'comum_nome':person['comum_congregacao'],
                     'municipio':person['municipio'],'situacao':'PRESENTE','local_id':site['id'],'observacoes':notes,
                     'created_by_user_id':'codex:confirmacao-presenca-solicitada',
                     'created_by_name':'Codex - confirmação solicitada pelo usuário',
                     'updated_by_user_id':'codex:confirmacao-presenca-solicitada',
                     'updated_by_name':'Codex - confirmação solicitada pelo usuário'})
Path('tmp/igor-wagner-presence-plan.json').write_text(json.dumps(payloads,ensure_ascii=False,indent=2),encoding='utf-8')
if '--apply' in sys.argv and payloads:
    response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_evento_encarregados',
                           headers=service_headers('return=representation'),json=payloads,timeout=20)
    if not response.ok:print(response.status_code,response.text)
    response.raise_for_status()
    assert len(response.json())==len(payloads)
    _invalidate_annual()
if '--apply' in sys.argv:
    rows,_=_reviews([{'id':event_id}])
    assert all(any(r['comum_chave']==key and r['encarregado_nome']==name and r['situacao']=='PRESENTE'
                   for r in rows) for name,key in expected)
print(json.dumps({'people':expected,'local':site['nome'],'new_records':len(payloads),'applied':'--apply' in sys.argv},ensure_ascii=True))
