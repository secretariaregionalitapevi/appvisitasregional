import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
import django
django.setup()
import requests
from copy import deepcopy
from collections import Counter
from django.conf import settings
from ColorAdminApp.modules.access_control import service_headers
from ColorAdminApp.modules.regional_routes import compact_period_groups, finalize_plan
from ColorAdminApp.utils.routing import haversine_distance

response = requests.get(settings.SUPABASE_URL + '/rest/v1/visitas_roteiros_regionais',
    headers=service_headers(), params={'select':'plano','order':'created_at.desc','limit':1,
                                    'plano->>deleted_at':'is.null'}, timeout=15)
response.raise_for_status()
original = response.json()[0]['plano']
updated = deepcopy(original)
baseline = finalize_plan(deepcopy(original))
compact_period_groups(updated['houses'], updated['groups'], updated.get('origins'))
finalize_plan(updated)
def distance(plan, group):
    current = group.get('origin')
    total = 0
    for house in sorted((h for h in plan['houses'] if h['group_id']==str(group['id'])),key=lambda h:h['number']):
        if current and house.get('coords'):
            total += haversine_distance(current,house['coords'])
        current = house.get('coords') or current
    return round(total)
before = sum(distance(original,g) for g in original['groups'])
after = sum(distance(updated,g) for g in updated['groups'])
old_assignments = {h['key']:h['group_id'] for h in original['houses']}
print({'before_straight_line_m':before,'after_straight_line_m':after,
       'before_with_current_period_rules_m':sum(distance(baseline,g) for g in baseline['groups']),
       'reassigned_houses':sum(old_assignments[h['key']]!=h['group_id'] for h in updated['houses']),
       'group_sizes':sorted(Counter(h['group_id'] for h in updated['houses']).values())})
for old_group,new_group in zip(original['groups'],updated['groups']):
    print({'group':new_group['nome'],'before_m':distance(original,old_group),'after_m':distance(updated,new_group),
           'departure_shift_m':round(haversine_distance(old_group['origin'],new_group['origin'])) if old_group.get('origin') and new_group.get('origin') else None})
