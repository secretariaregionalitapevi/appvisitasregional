import hashlib
import json
import sys
from pathlib import Path
import requests
from django.conf import settings
from ColorAdminApp.modules.music_events import _read, _registry, _invalidate_annual
from ColorAdminApp.modules.music_events_justifications import read_upload, reconcile, pack_metadata, metadata
from ColorAdminApp.modules.access_control import common_catalog, service_headers
from django.core.files.uploadedfile import SimpleUploadedFile

source=Path(r'c:\Users\Usuário\Downloads\JUSTIFICATIVA ENSAIOS REGIONAIS 15-11-2026 - COTIA - CAUCAIA - VGP -9H00  (respostas)  2.pdf')
content=source.read_bytes()
rows=reconcile(read_upload(SimpleUploadedFile(source.name,content)),common_catalog(),_registry(),'2026-11-15')
valid=[r for r in rows if not r['problema']]
assert len(valid)==5, [(r['nome'],r['problema']) for r in rows]
michel=next(r for r in valid if r['nome']=='MICHEL FRANK BONFIM CHAVES')
event_id='0c00b334-0ab6-4175-b759-028aef44161f'
existing=_read('musica_evento_encarregados',evento_id='eq.'+event_id,comum_chave='eq.'+michel['comum_chave'])
payload={'evento_id':event_id,'comum_chave':michel['comum_chave'],'comum_nome':michel['comum_identificada'],
         'municipio':michel['municipio'],'encarregado_nome':michel['nome'],'situacao':'JUSTIFICOU','local_id':None,
         'observacoes':pack_metadata({'origem':source.name,'lote':'pdf-'+hashlib.sha256(content).hexdigest(),
                                     'nome':michel['nome'],'cargo':michel['cargo'],'motivo':michel['motivo'],
                                     'bloco':michel.get('bloco_origem',''),'solicitado_pelo_usuario':True}),
         'created_by_user_id':'codex:correcao-justificativa-pdf','created_by_name':'Codex - correção solicitada pelo usuário',
         'updated_by_user_id':'codex:correcao-justificativa-pdf','updated_by_name':'Codex - correção solicitada pelo usuário'}
Path('tmp/michel-justification-plan.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
found=[r for r in existing if (r.get('encarregado_nome') or metadata(r.get('observacoes')).get('nome'))==michel['nome']]
if '--apply' in sys.argv and not found:
    response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_evento_encarregados',
                           headers=service_headers('return=representation'),json=payload,timeout=20)
    if not response.ok:
        error=response.json()
        if error.get('code')=='PGRST204' and 'encarregado_nome' in error.get('message',''):
            assert not existing, 'Não substituir conferência individual existente.'
            legacy={k:v for k,v in payload.items() if k!='encarregado_nome'}
            response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_evento_encarregados',
                                   headers=service_headers('return=representation'),json=legacy,timeout=20)
        if not response.ok:
            print(response.status_code,response.text)
    response.raise_for_status()
    _invalidate_annual()
    found=response.json()
print(json.dumps({'identified':len(valid),'michel':michel['nome'],'already_saved':bool(found),
                  'applied':'--apply' in sys.argv},ensure_ascii=True))
