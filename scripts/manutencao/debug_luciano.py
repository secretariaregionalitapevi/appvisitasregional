import requests

SUPABASE_URL = 'https://sqamxlhfazulrisiptud.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNxYW14bGhmYXp1bHJpc2lwdHVkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NzM3NTg4NCwiZXhwIjoyMDgyOTUxODg0fQ.w92yMKGGh5-ewRq0q6Pdl8TstzGlx0sGms1FCRveDYc'

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

print("Fetching Luciano...")
res_irm = requests.get(f"{SUPABASE_URL}/rest/v1/visitas_irmandade?nome=ilike.*LUCIANO*", headers=headers)
print(res_irm.json())

print("Fetching Agenda for Luciano...")
res_age = requests.get(f"{SUPABASE_URL}/rest/v1/visitas_agenda?titulo=ilike.*LUCIANO*", headers=headers)
print(res_age.json())
