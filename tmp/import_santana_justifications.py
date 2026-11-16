import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
import requests
from django.conf import settings
from ColorAdminApp.modules.access_control import service_headers
from ColorAdminApp.modules.music_events import _read, _reviews, _invalidate_annual
from ColorAdminApp.modules.music_events_import import norm
from ColorAdminApp.modules.music_events_justifications import metadata, pack_metadata

audit=json.loads(Path('tmp/santana-justifications-identification.json').read_text(encoding='utf-8'))
event=audit['event']
assert event['id']=='0c00b334-0ab6-4175-b759-028aef44161f' and event['data_evento']=='2026-11-15'
assert event['status']=='ABERTO'
explicit={'Adonias':'BR-22-2374','Elias':'BR-22-1806','Onofre':'BR-22-1251'}
plan=[]
for row in audit['rows']:
    if row['received_name']=='Jeferson':
        chosen={'name':'JEFFERSON DANIEL DE SOUZA','common':{'comum':'BR-21-1310 - PARQUE SINAI','cidade':'SANTANA DE PARNAÍBA'}}
    else:
        matches=[p for p in row['candidates'] if p['common']['comum'] in row['resolved_commons']]
        if row['received_name'] in explicit:
            matches=[p for p in row['candidates'] if p['common']['comum'].startswith(explicit[row['received_name']]+' - ')]
        assert len(matches)==1, row
        chosen=matches[0]
    plan.append({**row,'nome':chosen['name'],'common':chosen['common']})
assert len(plan)==13
assert len({(p['common']['comum'],norm(p['nome'])) for p in plan})==13
Path('tmp/santana-justifications-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
batch='mensagem-'+hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
groups=defaultdict(list)
for person in plan:
    key=person['common']['comum'].split(' - ',1)[0]
    groups[key].append(person)
existing=_read('musica_evento_encarregados',evento_id='eq.'+event['id'])
existing_by_common={row['comum_chave']:row for row in existing}
payloads=[]
for key,people in groups.items():
    previous=existing_by_common.get(key)
    if previous:
        info=metadata(previous.get('observacoes'))
        prior_names=[p['nome'] for p in info.get('pessoas',[])] or [previous.get('encarregado_nome') or info.get('nome','')]
        if {norm(p['nome']) for p in people}<={norm(n) for n in prior_names} and previous['situacao']=='JUSTIFICOU':
            continue
        raise RuntimeError('Conferência preexistente requer conciliação antes de gravar: '+key)
    individuals=[{'nome':p['nome'],'motivo':p['reason'],'situacao':'JUSTIFICOU','local_id':None,
                  'nome_recebido':p['received_name'],'comum_recebida':p['received_common']} for p in people]
    notes={'nome':' / '.join(p['nome'] for p in people),'motivo':' | '.join(p['nome']+': '+p['reason'] for p in people),
           'origem':'Mensagem encaminhada fornecida pelo usuário','lote':batch,'data_evento':'15/11/2026',
           'cargo':'Encarregado Local','pessoas':individuals}
    common=people[0]['common']
    payload={'evento_id':event['id'],'comum_chave':key,'comum_nome':common['comum'],'municipio':common['cidade'],
             'situacao':'JUSTIFICOU','local_id':None,'observacoes':pack_metadata(notes),
             'created_by_user_id':'codex:importacao-justificativas-mensagem',
             'created_by_name':'Codex - importação solicitada pelo usuário',
             'updated_by_user_id':'codex:importacao-justificativas-mensagem',
             'updated_by_name':'Codex - importação solicitada pelo usuário'}
    payloads.append(payload)
Path('tmp/santana-justifications-payloads.json').write_text(json.dumps(payloads,ensure_ascii=False,indent=2),encoding='utf-8')
if '--apply' in sys.argv and payloads:
    response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_evento_encarregados',
                           headers=service_headers('return=representation'),json=payloads,timeout=30)
    if not response.ok:print(response.status_code,response.text)
    response.raise_for_status()
    assert len(response.json())==len(payloads)
    _invalidate_annual()
if '--apply' in sys.argv:
    saved,_=_reviews([event])
    for person in plan:
        matches=[r for r in saved if r['comum_chave']==person['common']['comum'].split(' - ',1)[0]
                 and norm(r.get('encarregado_nome'))==norm(person['nome']) and r['situacao']=='JUSTIFICOU']
        assert len(matches)==1, person
print(json.dumps({'people':len(plan),'commons':len(groups),'new_common_records':len(payloads),'applied':'--apply' in sys.argv,
                  'people_identified':[(p['nome'],p['common']['comum']) for p in plan]},ensure_ascii=True))
