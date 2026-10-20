
import os
import requests

path = 'ColorAdminApp/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Substituição robusta para usar params no requests (OSM)
old_line = 'url_osm = f\"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1\"'
new_code = 'url_osm = "https://nominatim.openstreetmap.org/search"\\n\t\t\t\tparams_osm = {"q": address, "format": "json", "limit": 1}\\n\t\t\t\tresp_osm = requests.get(url_osm, headers=headers, params=params_osm, timeout=5)'

if old_line in content:
    content = content.replace(old_line, new_code)
    # Limpeza de possíveis linhas duplicadas de tentativas anteriores
    content = content.replace('resp_osm = requests.get(url_osm, headers=headers, timeout=5)', '')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Sucesso: Motor reserva blindado com sucesso.')
else:
    print('Status: O motor reserva já estava atualizado ou configurado.')
