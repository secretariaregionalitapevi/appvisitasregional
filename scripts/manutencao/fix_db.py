import requests

SUPABASE_URL = 'https://sqamxlhfazulrisiptud.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNxYW14bGhmYXp1bHJpc2lwdHVkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NzM3NTg4NCwiZXhwIjoyMDgyOTUxODg0fQ.w92yMKGGh5-ewRq0q6Pdl8TstzGlx0sGms1FCRveDYc'

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# 1. Obter todas as visitas sem irmandade_id
res_age = requests.get(f"{SUPABASE_URL}/rest/v1/visitas_agenda?irmandade_id=is.null", headers=headers)
agenda_orphans = res_age.json()
print(f"Found {len(agenda_orphans)} orphaned visits.")

# 2. Obter toda a irmandade
res_irm = requests.get(f"{SUPABASE_URL}/rest/v1/visitas_irmandade", headers=headers)
irmandade = res_irm.json()

# Mapa de nomes (maiúsculas) para ID
name_to_id = {i['nome'].strip().upper(): i['id'] for i in irmandade if i.get('nome')}

fixes = 0
for a in agenda_orphans:
    titulo = a.get('titulo')
    if titulo:
        titulo_upper = titulo.strip().upper()
        if titulo_upper in name_to_id:
            irm_id = name_to_id[titulo_upper]
            print(f"Fixing visit '{titulo}' with ID {irm_id}")
            # Patch
            patch_res = requests.patch(
                f"{SUPABASE_URL}/rest/v1/visitas_agenda?id=eq.{a['id']}",
                headers=headers,
                json={"irmandade_id": irm_id}
            )
            if patch_res.status_code in [200, 204]:
                fixes += 1
            else:
                print("Failed to patch:", patch_res.text)

print(f"Fixed {fixes} visits.")
