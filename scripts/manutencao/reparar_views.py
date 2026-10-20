
import os

path = 'ColorAdminApp/views.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_until = -1

for i, line in enumerate(lines):
    if i < skip_until:
        continue
    
    # Se chegarmos no ponto problemático da apiGeocode
    if 'return JsonResponse({\'error\': f\"Geocode falhou' in line:
        # Reescreve o final da função apiGeocode de forma limpa com TABS
        new_lines.append('\t\t\treturn JsonResponse({\'error\': f\"Geocode falhou: Google({result.get(\'status\')}) e Fallback falharam.\"}, status=400)\n')
        new_lines.append('\t\texcept Exception as e:\n')
        new_lines.append('\t\t\treturn JsonResponse({\'error\': str(e)}, status=500)\n')
        new_lines.append('\n')
        new_lines.append('\treturn JsonResponse({\'error\': \'Invalid request method\'}, status=405)\n')
        
        # Pula as linhas que estavam "sujas" (geralmente 4 ou 5 linhas)
        # Vamos procurar onde a próxima função começa
        for j in range(i + 1, len(lines)):
            if 'def ' in lines[j]:
                skip_until = j
                break
        continue
        
    new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Sucesso: O servidor foi reparado e a sintaxe está correta.')
