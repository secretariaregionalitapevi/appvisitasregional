from django.shortcuts import redirect
from django.http import JsonResponse
from datetime import datetime
import requests
from django.conf import settings

class SupabaseAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # List of paths that don't require authentication
        # Using hardcoded paths to avoid NoReverseMatch errors during template rendering/middleware execution
        exempt_paths = [
            '/user/login-v1',
            '/user/cadastro',
            '/api/auth/',
            '/visitas/navegar/',
            '/static/',
        ]
        
        # Check if current path is exempt
        path = request.path
        is_exempt = any(path.startswith(p) for p in exempt_paths)
        
        # If not exempt and no session, redirect to login
        if not is_exempt and not request.session.get('supabase_token'):
            return redirect('/user/login-v1')

        # A sessão Django é independente do Supabase Auth. Confirma o perfil em
        # toda requisição protegida para revogar imediatamente contas excluídas,
        # rejeitadas ou que perderam aprovação em outra máquina.
        if not is_exempt and request.session.get('supabase_token'):
            user_id = request.session.get('user_id')
            revoke_reason = None
            if not user_id:
                revoke_reason = 'invalid_session'
            else:
                try:
                    profile_response = requests.get(
                        f"{settings.SUPABASE_URL}/rest/v1/profiles",
                        headers={
                            'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
                            'Authorization': f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                        },
                        params={'user_id': f'eq.{user_id}', 'select': 'user_id,status', 'limit': '1'},
                        timeout=5,
                    )
                    if profile_response.status_code == 200:
                        profiles = profile_response.json()
                        if not profiles:
                            revoke_reason = 'account_removed'
                        elif profiles[0].get('status') != 'approved':
                            revoke_reason = 'access_revoked'
                except (requests.RequestException, ValueError):
                    # Falha de rede não deve expulsar todos os usuários ativos.
                    pass

            if revoke_reason:
                request.session.flush()
                if path.startswith(('/api/', '/visitas/api/', '/administracao/api/')):
                    return JsonResponse({
                        'error': 'Sua sessão foi encerrada porque este acesso não está mais ativo.',
                        'code': revoke_reason,
                    }, status=401)
                return redirect(f'/user/login-v1?reason={revoke_reason}')

        response = self.get_response(request)

        # Registra utilização real sem gerar ruído para APIs e arquivos estáticos.
        if request.method == 'GET' and request.session.get('user_id') and not any(
            path.startswith(prefix) for prefix in ('/api/', '/visitas/api/', '/administracao/api/', '/static/')
        ):
            try:
                from .views import log_audit
                log_audit(request, 'VIEW_PAGE', 'NAVIGATION', {
                    'path': path, 'view': getattr(getattr(request, 'resolver_match', None), 'url_name', None)
                })
                access_session_id = request.session.get('audit_access_session_id')
                if access_session_id:
                    requests.patch(
                        f"{settings.SUPABASE_URL}/rest/v1/audit_access_sessions",
                        headers={
                            'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
                            'Authorization': f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                            'Content-Type': 'application/json',
                        }, params={'id': f'eq.{access_session_id}'},
                        json={'last_activity_at': datetime.now().astimezone().isoformat()}, timeout=5,
                    )
            except Exception as exc:
                print(f"Failed to update audited activity: {exc}")
        return response
