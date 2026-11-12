import os,sys,json,hashlib,unicodedata
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from openpyxl import load_workbook
from ColorAdminApp import admin_views as a
from ColorAdminApp.modules import congregation_distribution as d
from ColorAdminApp.modules.music_events_identity import CommonResolver
from django.conf import settings
import requests
snapshot=json.loads(Path('tmp/itapevi-examinadoras-snapshot.json').read_text(encoding='utf-8'))
source=next(Path('d:/BACKUP GERAL/CCB - SECRETARIA MUSICAL/REGIONAL ITAPEVI').glob('*2025.xlsx'))
resolver=CommonResolver(snapshot['catalog'])
persons=d.directory(snapshot['people'],snapshot['overrides'])
def norm(v):return ' '.join(''.join(c for c in unicodedata.normalize('NFD',str(v).upper()) if not unicodedata.combining(c)).split())
common_aliases={'CENTRO':'BR-21-1039','JARDM BELA VISTA':'BR-22-0679','RECANTO DOS PASSAROS':'BR-21-1481'}
name_aliases={'MIRIAM FRANCISLINE MARIANO DE SOUSA MONTEIRO':'MIRIAN FRANCISLINE MARIANO DE SOUSA MONTEIRO'}
proposed=[]
for number,row in enumerate(load_workbook(source,data_only=True).worksheets[0].values,1):
 if number<8:continue
 assert norm(row[0])=='ITAPEVI' and row[5]
 target=resolver.resolve(common_aliases.get(norm(row[1]),row[1]),row[0]);assert target,row[1]
 code=d.common_code(target['comum'])
 matches=[p for p in persons.values() if 'examinadora' in p['roles'] and norm(p['nome'])==name_aliases.get(norm(row[5]),norm(row[5]))]
 assert len(matches)==1,(row[5],matches)
 person=matches[0]
 item=d.validate_assignments([{'role':'examinadora','person_id':person['person_id'],'residence_codes':person['residence_codes']}],persons,snapshot['catalog'],code)[0]
 item.update(congregation_code=code,source_document=source.name,source_row=number,source_sheet='Dados',source_column='F',source_name=row[5])
 proposed.append(item)
assert len(proposed)==51 and len({p['congregation_code'] for p in proposed})==51
counts=Counter(p['nome'] for p in proposed)
plan={'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'counts':dict(counts),'assignments':proposed}
Path('tmp/itapevi-examinadoras-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(counts),ensure_ascii=True))
if '--apply' not in sys.argv:sys.exit()
current=a._get_table(d.TABLE,{'select':'*','limit':'1000'})
by_code={r['congregation_code']:r for r in current}
old={r['congregation_code']:r for r in snapshot['overrides']}
for item in proposed:
 code=item['congregation_code'];assert by_code[code]==old[code],('Concurrent change',code)
Path('tmp/itapevi-examinadoras-before.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
changes=[]
for item in proposed:
 code=item['congregation_code'];before=by_code[code]
 assignments=[x for x in before['assignments'] if x['role']!='examinadora']+[item]
 if before['assignments']==assignments:continue
 payload={'assignments':assignments,'revision':before['revision']+1,'updated_by':'codex:user-request:itapevi-examinadoras','updated_at':datetime.now(timezone.utc).isoformat()}
 response=requests.patch(f'{settings.SUPABASE_URL}/rest/v1/{d.TABLE}',headers=a._headers('return=representation'),params={'congregation_code':f'eq.{code}','revision':f'eq.{before["revision"]}'},json=payload,timeout=20)
 response.raise_for_status();saved=response.json();assert len(saved)==1,('Concurrent change',code)
 changes.append({'before':before,'after':saved[0]})
 Path('tmp/itapevi-examinadoras-applied.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
 audit={'user_id':None,'action':'UPDATE','module':'ADMINISTRACAO_CONGREGACOES','details':{'entity':d.TABLE,'entity_id':code,'before':before,'after':saved[0],'outcome':'success','source_document':source.name,'source_sha256':plan['sha256'],'source_row':item['source_row'],'actor':{'name':'Codex - import requested by user'}},'user_agent':'Codex authorized spreadsheet import'}
 response=requests.post(f'{settings.SUPABASE_URL}/rest/v1/audit_logs',headers=a._headers(),json=audit,timeout=20);response.raise_for_status()
verified=a._get_table(d.TABLE,{'select':'*','limit':'1000'})
verified_by_code={r['congregation_code']:r for r in verified}
for item in proposed:
 code=item['congregation_code'];after=verified_by_code[code]
 assert [x for x in after['assignments'] if x['role']=='examinadora']==[item]
 assert [x for x in after['assignments'] if x['role']!='examinadora']==[x for x in old[code]['assignments'] if x['role']!='examinadora']
for code in set(by_code)-{x['congregation_code'] for x in proposed}:assert verified_by_code[code]==by_code[code]
seed_path=Path('ColorAdminApp/data/congregation_assignments.json');seed=json.loads(seed_path.read_text(encoding='utf-8'))
codes={x['congregation_code'] for x in proposed}
seed['assignments']=[x for x in seed['assignments'] if not(x['role']=='examinadora' and x['congregation_code'] in codes)]+proposed
seed['pending']=[x for x in seed.get('pending',[]) if not(x.get('role')=='examinadora' and x.get('congregation_code') in codes)]
seed['sources']=[x for x in seed['sources'] if x['name']!=source.name]+[{'name':source.name,'sha256':plan['sha256']}]
seed_path.write_text(json.dumps(seed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('VERIFIED',len(proposed),'assignments;',len(changes),'updated records; other roles and municipalities preserved')
