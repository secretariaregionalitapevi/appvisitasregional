import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
django.setup()
from django.conf import settings
import requests

url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS}"
headers = {
    'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
    'Content-Type': 'application/json'
}

requests.patch(f"{url}?id=eq.58790d86-8771-46c0-adc1-65a1110544be", headers=headers, json={
    'gvi': 2,
    'total_visitas': 2
})
print("Patched lost visit in June")
