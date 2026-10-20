import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
django.setup()
from django.conf import settings
import requests
import json

url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS}"
headers = {
    'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
    'Content-Type': 'application/json'
}

res = requests.get(url, headers=headers)
print(json.dumps(res.json(), indent=2))
