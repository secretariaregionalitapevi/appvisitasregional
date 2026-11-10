"""Sistema centralizado de auditoria para todos os módulos.

Fornece funções genéricas para criar dashboards de auditoria
para qualquer módulo que tenha dados auditados em Supabase.
"""
import requests
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.conf import settings
from .access_control import can_access, service_headers, user_scope, scope_details
from .module_access import can_access_module

# Mapeamento de módulos com suporte a auditoria
AUDIT_MODULES = {
    "musicalizacao": {
        "display_name": "Musicalização Infantil",
        "icon": "fa-music",
        "resources": {
            "aulas": {
                "table": "musicalizacao_aulas",
                "select": "id,data_aula,polo,cidade,created_by_user_id,created_by_name,created_by_email,created_at,updated_by_user_id,updated_by_name,updated_by_email,updated_at",
                "description": "Atividades (Aulas)",
                "icon": "fa-calendar",
            },
            "presencas": {
                "table": "musicalizacao_presenca",
                "select": "id,aula_id,aluno_id,created_by_user_id,created_by_name,created_by_email,created_at",
                "description": "Presenças",
                "icon": "fa-check",
            },
        },
    },
    "darpe": {
        "display_name": "DARPE (Serviços)",
        "icon": "fa-handshake",
        "resources": {
            "atendimentos": {
                "table": "darpe_atendimentos",
                "select": "id,data_atendimento,visitante_nome,origem,created_by_user_id,created_by_name,created_by_email,created_at,updated_by_user_id,updated_by_name,updated_by_email,updated_at",
                "description": "Atendimentos",
                "icon": "fa-user-check",
            },
        },
    },
    "cartas": {
        "display_name": "Cartas de Exames",
        "icon": "fa-envelope",
        "resources": {
            "cartas": {
                "table": "cartas_exames",
                "select": "id,nome_examinando,data_entrega,status,created_by_user_id,created_by_name,created_by_email,created_at,updated_by_user_id,updated_by_name,updated_by_email,updated_at",
                "description": "Cartas de Exames",
                "icon": "fa-certificate",
            },
        },
    },
    "visitas": {
        "display_name": "Programa de Visitas",
        "icon": "fa-person-hiking",
        "resources": {
            "visitas": {
                "table": "visitas_apontamentos",
                "select": "id,data_visita,irmandade_id,irmandade_nome,comum_congregacao,created_by_user_id,created_by_name,created_by_email,created_at,updated_by_user_id,updated_by_name,updated_by_email,updated_at",
                "description": "Apontamentos de Visitas",
                "icon": "fa-check-double",
            },
        },
    },
    "sam": {
        "display_name": "Sistema de Acompanhamento Musical",
        "icon": "fa-graduation-cap",
        "resources": {
            "eventos": {
                "table": "sam_audit_events",
                "select": "id,action_type,actor_name_snapshot,congregation_snapshot,occurred_at,target_type,target_name_snapshot,synced_at",
                "description": "Eventos de Auditoria",
                "icon": "fa-history",
            },
        },
    },
    "gem": {
        "display_name": "GEM (Educação Musical)",
        "icon": "fa-book",
        "resources": {
            "aulas": {
                "table": "gem_aulas",
                "select": "id,data_aula,professor_id,professor_nome,created_by_user_id,created_by_name,created_by_email,created_at,updated_by_user_id,updated_by_name,updated_by_email,updated_at",
                "description": "Aulas GEM",
                "icon": "fa-chalkboard",
            },
        },
    },
}

def get_audit_modules():
    """Retorna lista de módulos com suporte a auditoria."""
    return AUDIT_MODULES

def api_audit_generic(request, module):
    """API genérica para consultar auditoria de qualquer módulo.
    
    GET /api/auditoria/generic/?module=musicalizacao&resource=aulas&period=30
    """
    if not can_access_module(request, module):
        return JsonResponse({"error": "Acesso negado a este módulo."}, status=403)
    
    if request.method.upper() != "GET":
        return JsonResponse({"error": "Apenas GET permitido."}, status=405)
    
    scope = user_scope(request)
    config = AUDIT_MODULES.get(module)
    
    if not config:
        return JsonResponse({"error": "Módulo de auditoria não encontrado."}, status=404)
    
    try:
        resource = request.GET.get('resource', '')
        action = request.GET.get('action', '')
        operator = request.GET.get('operator', '')
        period = int(request.GET.get('period', 30))
        
        if period < 1 or period > 3650:
            return JsonResponse({"error": "Período deve estar entre 1 e 3650 dias."}, status=400)
        
        cutoff_date = (datetime.now() - timedelta(days=period)).isoformat()
        all_records = []
        unique_operators = set()
        
        # Processar cada recurso do módulo
        for res_name, res_config in config['resources'].items():
            if resource and resource != res_name:
                continue
            
            try:
                # Montar parâmetros de filtro
                params = {
                    'select': res_config['select'],
                    'order': 'created_at.desc',
                    'limit': '100',
                }
                
                # Filtrar por data
                if 'created_at' in res_config['select']:
                    params['created_at'] = f'gte.{cutoff_date}'
                
                # Fazer requisição ao Supabase
                response = requests.get(
                    f"{settings.SUPABASE_URL}/rest/v1/{res_config['table']}",
                    headers=service_headers(),
                    params=params,
                    timeout=15
                )
                response.raise_for_status()
                rows = response.json()
                
                # Filtrar por escopo
                for row in rows:
                    # Verificar escopo (se aplicável)
                    if 'cidade' in row and 'polo' in row:
                        if not can_access(scope, {'cidade': row.get('cidade'), 'comum': row.get('polo')}):
                            continue
                    elif 'cidade' in row:
                        if not can_access(scope, {'cidade': row.get('cidade')}):
                            continue
                    
                    creator_name = row.get('created_by_name') or row.get('actor_name_snapshot') or 'Sistema'
                    updater_name = row.get('updated_by_name')
                    
                    # Filtrar por operador
                    if operator:
                        if operator.lower() not in creator_name.lower() and (not updater_name or operator.lower() not in updater_name.lower()):
                            continue
                    
                    unique_operators.add(creator_name)
                    if updater_name:
                        unique_operators.add(updater_name)
                    
                    # Filtrar por ação
                    action_type = 'Criação'
                    if updater_name and not action:
                        action_type = 'Atualização'
                    elif action == 'created':
                        action_type = 'Criação'
                    elif action == 'updated':
                        action_type = 'Atualização'
                    
                    # Formatar registro
                    all_records.append({
                        'resource': res_config['description'],
                        'action': action_type,
                        'created_by': creator_name,
                        'created_at': row.get('created_at') or row.get('occurred_at'),
                        'details': f"Registro ID: {row.get('id')}",
                    })
            except requests.RequestException:
                # Falha silenciosa para um recurso, continua com os outros
                continue
        
        # Ordenar por data descendente
        all_records.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return JsonResponse({
            "records": all_records,
            "total_events": len(all_records),
            "active_operators": len(unique_operators),
            "scope": "REGIONAL" if scope == "global" else "MUNICIPAL",
        }, status=200)
        
    except ValueError:
        return JsonResponse({"error": "Parâmetros numéricos inválidos."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Erro ao consultar auditoria: {str(e)}"}, status=500)
