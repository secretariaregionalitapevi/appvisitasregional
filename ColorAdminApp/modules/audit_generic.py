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
    
    GET /api/auditoria/generic/?module=musicalizacao&resource=aulas&days=30
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
        actor = request.GET.get('actor', '')
        days = int(request.GET.get('days', 30))
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))
        
        if days < 1 or days > 3650:
            return JsonResponse({"error": "Dias deve estar entre 1 e 3650."}, status=400)
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        results = {}
        
        # Processar cada recurso do módulo
        for res_name, res_config in config['resources'].items():
            if resource and resource != res_name:
                continue
            
            # Montar parâmetros de filtro
            params = {
                'select': res_config['select'],
                'order': 'created_at.desc',
                'limit': limit,
                'offset': offset,
            }
            
            # Filtrar por data
            if 'created_at' in res_config['select']:
                params['created_at'] = f'gte.{cutoff_date}'
            
            # Filtrar por ação
            if action == 'created':
                params['created_by_user_id'] = 'not.is.null'
            elif action == 'updated':
                params['updated_by_user_id'] = 'not.is.null'
            
            # Fazer requisição ao Supabase
            response = requests.get(
                f"{settings.SUPABASE_URL}/rest/v1/{res_config['table']}",
                headers=service_headers(),
                params=params,
                timeout=15
            )
            response.raise_for_status()
            rows = response.json()
            
            # Filtrar por escopo e ator
            filtered = []
            for row in rows:
                # Verificar escopo (se aplicável)
                if 'cidade' in row and 'polo' in row:
                    if not can_access(scope, {'cidade': row.get('cidade'), 'comum': row.get('polo')}):
                        continue
                
                # Filtrar por ator
                if actor:
                    creators = [row.get('created_by_name'), row.get('updated_by_name')]
                    if not any(actor.lower() in (name or '').lower() for name in creators):
                        continue
                
                # Formatar registro
                filtered.append({
                    'resource': res_name,
                    'id': row.get('id'),
                    'description': res_config['description'],
                    'created_by': row.get('created_by_name') or row.get('actor_name_snapshot'),
                    'created_at': row.get('created_at') or row.get('occurred_at'),
                    'updated_by': row.get('updated_by_name'),
                    'updated_at': row.get('updated_at'),
                })
            
            results[res_name] = filtered
        
        return JsonResponse({
            "results": results,
            "module": {
                "name": module,
                "display_name": config['display_name'],
                "icon": config['icon'],
            },
            "scope": scope_details(scope),
            "filters": {
                "resource": resource,
                "action": action,
                "actor": actor,
                "days": days,
                "limit": limit,
                "offset": offset,
            }
        }, status=200)
        
    except ValueError:
        return JsonResponse({"error": "Parâmetros numéricos inválidos."}, status=400)
    except requests.RequestException as e:
        return JsonResponse({"error": f"Falha ao consultar auditoria: {str(e)}"}, status=502)
