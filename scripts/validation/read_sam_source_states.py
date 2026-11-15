"""Read-only snapshot of the current SAM source catalog, without student names."""
import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from ColorAdminApp.modules.music_events import _read


def main():
    rows=_read('sam_student_sync_state',select='source_key,aluno_id,source_common,source_instrument,source_level,source_payload,missing_since,last_seen_at',order='source_key.asc')
    safe=[]
    for row in rows:
        payload=row.get('source_payload') or {}
        safe.append({**row,'source_payload':{k:payload.get(k) for k in
                    ('ministry','city','source_city','resolved_common','instrument','level','common_name','member_type')}})
    out=Path('tmp/sam-base-reconciliation');out.mkdir(parents=True,exist_ok=True)
    (out/'source-states.json').write_text(json.dumps(safe,ensure_ascii=False,default=str),encoding='utf-8')
    active=[r for r in safe if not r.get('missing_since')]
    print('SAM catalog states:',len(rows),'current:',len(active),'missing:',len(rows)-len(active))
    print('Current source roles:',dict(Counter((r.get('source_payload') or {}).get('ministry') for r in active)))
    print('Last seen:',max(str(r.get('last_seen_at') or '') for r in active))


if __name__=='__main__':
    main()
