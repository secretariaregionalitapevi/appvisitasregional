
import os
import json
import requests

path = 'ColorAdminApp/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

new_osm = \"\"\"			try:
				# Nominatim requer um User-Agent descritivo
				headers = {'User-Agent': 'ColorAdmin-Ministerial-App/1.0'}
				url_osm = "https://nominatim.openstreetmap.org/search"
				params_osm = {'q': address, 'format': 'json', 'limit': 1}
				resp_osm = requests.get(url_osm, headers=headers, params=params_osm, timeout=5)
				result_osm = resp_osm.json()
				
				if result_osm and len(result_osm) > 0:
					print(f"GEOCODE: Sucesso via OSM para {address}")
					return JsonResponse({
						'lat': float(result_osm[0]['lat']),
						'lng': float(result_osm[0]['lon']),
						'formatted_address': result_osm[0]['display_name'],
						'source': 'osm'
					})
			except Exception as osm_e:
				print(f"GEOCODE: Erro fallback OSM: {osm_e}")
\"\"\"

start_marker = \"if result.get('status') != 'OK':\"
end_marker = \"if result.get('status') == 'OK':\"
start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + start_marker + \"\\n\" + new_osm + \"\\t\\t\" + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Sucesso: views.py atualizado com motor turbo.')
else:
    print('Erro: Marcadores não encontrados no views.py')
