import json
from pathlib import Path
import requests
from django.conf import settings
from ColorAdminApp.modules.music_events import _read, _reviews, _invalidate_annual
from ColorAdminApp.modules.access_control import service_headers

event_id='0c00b334-0ab6-4175-b759-028aef44161f'
rows=_read('musica_evento_presencas',evento_id='eq.'+event_id,nome='eq.JEFFERSON DANIEL DE SOUZA')
assert len(rows)==1
row=rows[0]
assert row['id']=='50320bc7-1c67-4eaf-97e5-7f15b5ce9700'
assert row['comum_informada']=='BR-21-1310 - PARQUE SINAI'
saved,_=_reviews([{'id':event_id}])
assert any(r.get('encarregado_nome')=='JEFFERSON DANIEL DE SOUZA' and r['situacao']=='JUSTIFICOU' for r in saved)
if row['situacao']!='JUSTIFICADO':
    assert row['situacao']=='PRESENTE'
    Path('tmp/jefferson-attendance-before-correction.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    payload={'situacao':'JUSTIFICADO',
             'observacoes':(row.get('observacoes') or '')+'\nCorreção expressa do usuário: não compareceu ao ensaio; manter somente a justificativa.',
             'updated_by_user_id':'codex:correcao-presenca-solicitada',
             'updated_by_name':'Codex - correção solicitada pelo usuário'}
    response=requests.patch(settings.SUPABASE_URL+'/rest/v1/musica_evento_presencas',
        headers=service_headers('return=representation'),json=payload,
        params={'id':'eq.'+row['id'],'evento_id':'eq.'+event_id,'situacao':'eq.PRESENTE'},timeout=20)
    if not response.ok:print(response.status_code,response.text)
    response.raise_for_status()
    assert len(response.json())==1
    _invalidate_annual()
assert _read('musica_evento_presencas',id='eq.'+row['id'])[0]['situacao']=='JUSTIFICADO'
print('Jefferson: lançamento nominal corrigido para JUSTIFICADO; justificativa individual preservada.')
