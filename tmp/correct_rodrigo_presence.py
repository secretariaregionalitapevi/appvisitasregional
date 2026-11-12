import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from ColorAdminApp.modules import music_ministry as api
from ColorAdminApp.modules import music_events
snapshot=json.loads(Path('tmp/pdfs/ministry-matrix/data.json').read_text(encoding='utf-8'))
person=next(r for r in snapshot['rows'] if r['nome'].upper()=='RODRIGO VIDAL DOS SANTOS')
event=next(e for e in snapshot['event_options'] if str(e['date'])=='2026-09-20')
assert event['id'].startswith('legado:')
event_id=event['id'].split(':',1)[1]
events=music_events._read('musica_eventos',id='eq.'+event_id)
assert len(events)==1 and str(events[0]['data_evento'])=='2026-09-20'
reviews=music_events._read('musica_ministerio_legado_conferencias',event_id='eq.'+event_id)
old=[r for r in reviews if r['person_key'] in person['aliases']];assert len(old)<=1
print('PERSON',person['nome'],person['comum']);print('EVENT',events);print('BEFORE',old)
Path('tmp/rodrigo-presence-before.json').write_text(json.dumps({'events':events,'reviews':old,'person':person},ensure_ascii=False,indent=2),encoding='utf-8')
if '--apply' in sys.argv:
 result=api._rpc('musica_ministerio_conferir_legado',{'p_evento':event_id,'p_pessoa':{'person_key':old[0]['person_key'] if old else person['key'],'nome':person['nome'],'comum':person['comum'],'municipio':person['municipio'],'roles':person['roles'],'situacao':'PRESENTE','observacoes':'Presenca no Ensaio Regional de 20/09/2026 confirmada expressamente pelo usuario.'},'p_version':old[0]['version'] if old else 0,'p_usuario_id':'codex:user-request','p_usuario_nome':'Codex - correcao solicitada pelo usuario'})
 print('AFTER',result)
 Path('tmp/rodrigo-presence-after.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 from django.core.cache import cache
 cache.delete('music-ministry:sources:v4:2026')
