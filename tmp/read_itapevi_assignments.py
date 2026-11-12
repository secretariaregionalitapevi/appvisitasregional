import os,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from ColorAdminApp import admin_views as a
from ColorAdminApp.modules import congregation_distribution as d
catalog=d.corrected_catalog(a.common_catalog())
rows,people=a._congregation_data(include_archived=True,include_people=True)
ov,editable=d.load_overrides(a._get_table)
Path('tmp/itapevi-examinadoras-snapshot.json').write_text(json.dumps({'catalog':catalog,'people':people,'rows':rows,'overrides':ov},ensure_ascii=False,indent=2),encoding='utf-8')
print('snapshot saved',len(catalog),len(people),len(ov),editable)
