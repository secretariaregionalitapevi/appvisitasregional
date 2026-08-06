from django.shortcuts import redirect
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
            '/user/register-v3',
            '/api/auth/',
            '/static/',
        ]
        
        # Check if current path is exempt
        path = request.path
        is_exempt = any(path.startswith(p) for p in exempt_paths)
        
        # If not exempt and no session, redirect to login
        if not is_exempt and not request.session.get('supabase_token'):
            return redirect('/user/login-v1')

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
