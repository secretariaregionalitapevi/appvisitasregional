"""Read-only SAM reconciliation: regional scope versus rehearsal-cycle scope."""
import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()

from ColorAdminApp.modules.access_control import common_catalog
from ColorAdminApp.modules.music_events import _registry
from ColorAdminApp.modules.music_events_dashboard import REGIONAL, regional_city
from ColorAdminApp.modules.music_events_import import norm
from ColorAdminApp.modules.music_events_participation import participation


def main():
    out=Path('tmp/sam-base-reconciliation');out.mkdir(parents=True,exist_ok=True)
    saved=out/'source.json'
    if saved.exists():
        source=json.loads(saved.read_text(encoding='utf-8'))
    else:
        registry=_registry()
        catalog=common_catalog()
        fields=('id','status','nivel','instrumento','cargo_ministerio','comum_congregacao','municipio','updated_at')
        source={'registry':[{key:row.get(key) for key in fields} for row in registry],'catalog':catalog}
        saved.write_text(json.dumps(source,ensure_ascii=False,default=str),encoding='utf-8')
    registry,catalog=source['registry'],source['catalog']
    print('SAM source rows:',len(registry),'unique IDs:',len({r['id'] for r in registry}))
    print('Status:',dict(Counter(norm(r.get('status')) for r in registry)))
    print('Municipalities:',dict(Counter(regional_city(r.get('municipio')) for r in registry)))
    event=dict(id='audit',titulo='Reconciliação SAM',tipo='ENSAIO_REGIONAL',familia='GERAL',data_evento='2026-11-15')
    for label,cities in [('Regional - sete municípios',REGIONAL),('Ciclo de novembro',
            ['CAUCAIA DO ALTO','COTIA','JANDIRA','SANTANA DE PARNAÍBA','VARGEM GRANDE PAULISTA'])]:
        result=participation({'events':[event],'filters':{'municipios':cities}},registry,[],catalog)
        print(label,{r['label']:r['registered'] for r in result['summaries']})
        print('Diagnostics:',{k:result[k] for k in ('unresolved_registry','undefined_instrument')})
        print('By city:',{city:{r['label']:r['registered'] for r in result['rows']
                               if r['city']==city and r['group'] in {'MUSICO','ORGANISTA'}} for city in cities})


if __name__=='__main__':
    main()
