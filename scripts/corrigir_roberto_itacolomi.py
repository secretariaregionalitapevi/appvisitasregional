"""Correct the identity and common explicitly confirmed by the user."""
import json
from pathlib import Path
import requests
from django.conf import settings
from django.core.cache import cache
from ColorAdminApp.modules.access_control import service_headers
from ColorAdminApp.modules.music_events import _read
from ColorAdminApp.modules.music_ministry import _rpc

def main():
    oldkey='irmandade:3936d84c-cf82-47e5-854a-42957b76dbe8'
    targetkey='sam:94aae6fa-6b40-4af3-979d-9d747a928ea8'
    table=settings.SUPABASE_TABLE_VISITAS_IRMANDADE
    member=_read(table,id='eq.'+oldkey.split(':')[1])[0]
    entries=_read('musica_ministerio_participacoes',person_key='eq.'+oldkey)
    directory=_read('musica_ministerio_pessoas',person_key='eq.'+oldkey)
    backup=Path('tmp/conciliacao_bras_confirmada/roberto_antes.json')
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():backup.write_text(json.dumps({'member':member,'entries':entries,'directory':directory},ensure_ascii=False,indent=2),encoding='utf-8')
    def patch(table,params,payload):
        response=requests.patch(settings.SUPABASE_URL+'/rest/v1/'+table,headers=service_headers(),params=params,json=payload,timeout=25)
        response.raise_for_status()
    for old in entries:
        targets=_read('musica_ministerio_participacoes',event_id='eq.'+old['event_id'],person_key='eq.'+targetkey)
        assert len(targets)==1, 'Canonical participation missing'
        target=targets[0]
        assert old['situacao'] in ('SEM_REGISTRO','NAO_APLICA'), 'Review unexpected positive attendance'
        _rpc('musica_ministerio_conferir',{'p_evento':old['event_id'],'p_pessoa':oldkey,'p_situacao':'NAO_APLICA','p_observacoes':'Duplicate identity corrected by user: ROBERTO FERREIRA, BR-22-3270 - JARDIM ITACOLOMI. Original record retained in audit.','p_version':old['version'],'p_usuario_id':'codex:correcao-confirmada','p_usuario_nome':'Correcao solicitada pelo usuario'})
        source={**old.get('source',{}),'canonical_person_key':targetkey,'canonical_name':target['nome'],'original_name':old['nome'],'original_common':old['comum'],'identity_confirmed_by':'usuario'}
        patch('musica_ministerio_participacoes',{'event_id':'eq.'+old['event_id'],'person_key':'eq.'+oldkey},{'source':source})
        response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_ministerio_auditoria',headers=service_headers(),json={'event_id':old['event_id'],'person_key':oldkey,'operacao':'CORRIGIR_IDENTIDADE_COMUM_CONFIRMADA','anterior':{'member':member,'entry':old},'posterior':{'source':source,'nome':target['nome'],'comum':target['comum']},'usuario_id':'codex:correcao-confirmada','usuario_nome':'Correcao solicitada pelo usuario'},timeout=25)
        response.raise_for_status()
    patch(table,{'id':'eq.'+oldkey.split(':')[1]},{'nome':'ROBERTO FERREIRA','comum':'BR-22-3270 - JARDIM ITACOLOMI','codigo_comum':'BR-22-3270'})
    patch('musica_ministerio_pessoas',{'person_key':'eq.'+oldkey},{'roles':[]})
    cache.delete('music-ministry:sources:v3:2026')
    print('Corrected Roberto identity and common; audit and backup saved.',flush=True)
