import json
from pathlib import Path
from django.core.files.uploadedfile import SimpleUploadedFile
from ColorAdminApp.modules.music_events_justifications import read_upload, reconcile
from ColorAdminApp.modules.music_events import _registry, _read, _reviews
from ColorAdminApp.modules.access_control import common_catalog
from ColorAdminApp.modules.music_events_import import is_conductor_role
path=Path(r'c:\Users\Usuário\Downloads\JUSTIFICATIVA ENSAIOS REGIONAIS 15-11-2026 - COTIA - CAUCAIA - VGP -9H00  (respostas)  2.pdf')
parsed=read_upload(SimpleUploadedFile(path.name,path.read_bytes()))
parsed=[r for r in parsed if is_conductor_role(r.get('cargo'))]
matched=reconcile(parsed,common_catalog(),_registry(),'2026-11-15')
events=_read('musica_eventos',data_evento='eq.2026-11-15',order='created_at.desc')
saved,_=_reviews(events[:1])
print(json.dumps({'parsed':parsed,'matched':matched,'saved':saved},ensure_ascii=True))
Path('tmp/justifications-audit.json').write_text(json.dumps({'matched':matched,'saved':saved,'event':events[0]},ensure_ascii=False),encoding='utf-8')
