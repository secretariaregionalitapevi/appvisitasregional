import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from django.test import RequestFactory
from unittest.mock import patch
from ColorAdminApp.modules import music_ministry as api
request=RequestFactory().get('/',{'ano':'2026','municipio':['ITAPEVI'],'cargo':'ENCARREGADO_LOCAL','atualizar':'1'})
request.session={}
with patch.object(api,'user_scope',return_value={'level':'global'}):data=api.dashboard_data(request)
keys={'sam:4a3a23b8-a665-4ac9-99db-f9af2667b3f8','sam:3ae914f3-5941-45a4-acc9-b7cb00e1cc39'}
rows=[r for r in data['rows'] if keys.intersection(r['aliases'])]
assert len(rows)==1,[(r['nome'],r['aliases']) for r in rows]
row=rows[0];assert row['nome']=='Os\u00e9ia de Souza'
states={str(c['date']):c['situacao'] for c in row['cells']}
for day in ['2026-01-18','2026-05-17','2026-07-19','2026-09-20']:assert states[day]=='PRESENTE',(day,states)
assert states['2026-10-06']=='SEM_REGISTRO'
assert row['present']==4
Path('tmp/oseia-after.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
print('Verified one identity, correct name, four presences and October absence',states)
