import os,sys,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from ColorAdminApp.modules.music_events import _read
IDS=['4a3a23b8-a665-4ac9-99db-f9af2667b3f8','3ae914f3-5941-45a4-acc9-b7cb00e1cc39']
keys=['sam:'+i for i in IDS]
queries=[('registry','musica_acompanhamento_aluno',{'id':'in.('+','.join(IDS)+')'}),('entries','musica_ministerio_participacoes',{'person_key':'in.('+','.join(keys)+')'}),('directory','musica_ministerio_pessoas',{'person_key':'in.('+','.join(keys)+')'}),('reviews','musica_ministerio_legado_conferencias',{'person_key':'in.('+','.join(keys)+')'})]
with ThreadPoolExecutor(max_workers=4) as pool:
 futures=[(label,pool.submit(_read,table,**params)) for label,table,params in queries]
 data={label:f.result() for label,f in futures}
Path('tmp/oseia-before.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
for label,rows in data.items():
 print(label)
 for row in rows:print({k:v for k,v in row.items() if k in ['id','nome_aluno','nome','person_key','event_id','source','situacao','version','comum_congregacao','roles','status']})
