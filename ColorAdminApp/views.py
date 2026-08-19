from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import generic
from django.http import HttpResponse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import re
import unicodedata
from urllib.parse import urlencode
from .access_control import can_access, common_catalog, filter_rows, scope_details, user_scope, visible_commons


def normalize_visit_team(value):
    """Converte nomes legados da equipe para o formato atual (ex.: Equipe 01 -> Equipe 1)."""
    name = ' '.join(str(value or '').strip().split())
    match = re.fullmatch(r'equipe(?:\s+de\s+visitas?)?\s+0*(\d+)', name, flags=re.IGNORECASE)
    return f'Equipe {int(match.group(1))}' if match else name


VISIT_PERIOD_MARKER_RE = re.compile(r'\s*\[\[periodo_planejado:(manha|tarde|noite)\]\]\s*', re.IGNORECASE)
VISIT_TIME_MARKER_RE = re.compile(r'\s*\[\[horario_(inicio|fim):(\d{1,2}:\d{2})\]\]\s*', re.IGNORECASE)


def split_visit_period_metadata(notes):
    text = str(notes or '')
    match = VISIT_PERIOD_MARKER_RE.search(text)
    visible = VISIT_PERIOD_MARKER_RE.sub(' ', text)
    visible = re.sub(r'\s{2,}', ' ', visible).strip()
    return visible, (match.group(1).lower() if match else '')


def split_visit_time_metadata(notes):
    """Separa os marcadores de horario do texto visivel da observacao."""
    text = str(notes or '')
    times = {
        match.group(1).lower(): match.group(2)
        for match in VISIT_TIME_MARKER_RE.finditer(text)
    }
    visible = VISIT_TIME_MARKER_RE.sub(' ', text)
    visible = re.sub(r'\s{2,}', ' ', visible).strip()
    return visible, times


def merge_visit_time_metadata(notes, times):
    visible, _ = split_visit_time_metadata(notes)
    markers = ' '.join(
        f'[[horario_{key}:{times[key]}]]'
        for key in ('inicio', 'fim') if times.get(key)
    )
    return f'{visible}{" " if visible and markers else ""}{markers}'


def visit_duration_minutes(times):
    try:
        start = datetime.strptime(times.get('inicio', ''), '%H:%M')
        end = datetime.strptime(times.get('fim', ''), '%H:%M')
        minutes = int((end - start).total_seconds() // 60)
        return minutes if minutes >= 0 else minutes + (24 * 60)
    except (TypeError, ValueError):
        return None


def apply_actual_visit_times(visit, times):
    """Aplica no evento os horarios reais registrados pelo app mobile."""
    start_time = str(times.get('inicio') or '').strip()
    end_time = str(times.get('fim') or '').strip()
    if not start_time and not end_time:
        return visit

    original_start = visit.get('data_inicio')
    try:
        from dateutil import parser
        parsed_start = parser.parse(str(original_start))
        if parsed_start.tzinfo:
            parsed_start = parsed_start.astimezone(ZoneInfo('America/Sao_Paulo'))
        visit_date = parsed_start.strftime('%Y-%m-%d')
    except (TypeError, ValueError, OverflowError):
        visit_date = str(original_start or '')[:10]

    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', visit_date):
        return visit
    if start_time:
        visit['data_inicio'] = f'{visit_date}T{start_time}:00-03:00'
    if end_time:
        visit['data_fim'] = f'{visit_date}T{end_time}:00-03:00'
    return visit


def normalized_visit_identity(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char)).casefold()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', normalized).split())


def normalized_visit_address(value):
    without_coordinates = re.sub(r'^\s*\[[^\]]+\]\s*', '', str(value or ''))
    return normalized_visit_identity(without_coordinates)


def unique_member_for_orphan_visit(visit, members):
    """Localiza com seguranca o recadastro correspondente a uma agenda orfa."""
    visit_name = normalized_visit_identity(
        re.sub(r'^\s*visita\s*(?:-|–|—)?\s*', '', str(visit.get('titulo') or ''), flags=re.IGNORECASE)
    )
    visit_address = normalized_visit_address(visit.get('endereco_visitado'))
    if not visit_name:
        return None
    name_matches = [
        member for member in members
        if normalized_visit_identity(member.get('nome')) == visit_name
    ]
    if visit_address:
        address_matches = [
            member for member in name_matches
            if normalized_visit_address(member.get('endereco')) == visit_address
        ]
        if len(address_matches) == 1:
            return address_matches[0]
    # Enderecos podem mudar entre a visita historica e o recadastro. O nome
    # completo ainda e seguro quando existe uma unica pessoa assim na comum.
    return name_matches[0] if len(name_matches) == 1 else None


def merge_visit_period_metadata(notes, period):
    visible, _ = split_visit_period_metadata(notes)
    return f'{visible}{" " if visible else ""}[[periodo_planejado:{period}]]' if period else visible


def normalize_regional_group(value):
    name = ' '.join(str(value or '').strip().split())
    match = re.fullmatch(r'(?:grupo|equipe)(?:\s+regional)?\s+([a-z])', name, flags=re.IGNORECASE)
    return f'Grupo {match.group(1).upper()}' if match else name


def visit_team_type(value):
    name = normalize_regional_group(value)
    return 'REGIONAL' if re.fullmatch(r'Grupo\s+[A-Z]', name) else 'LOCAL'


def normalize_team_name(value, team_type=None):
    normalized_type = str(team_type or '').strip().upper()
    return normalize_regional_group(value) if normalized_type == 'REGIONAL' else normalize_visit_team(value)


def format_display_name(value):
    """Padroniza nomes para exibição sem alterar siglas usuais do projeto."""
    text = ' '.join(str(value or '').strip().split())
    if not text:
        return ''
    lowercase_words = {'a', 'as', 'da', 'das', 'de', 'do', 'dos', 'e'}
    acronyms = {'ccb', 'gve', 'gvi', 'gvm', 're', 'rf'}
    words = []
    for index, word in enumerate(text.split(' ')):
        parts = []
        for part in word.split('-'):
            clean = part.casefold()
            if clean in acronyms:
                parts.append(clean.upper())
            elif index > 0 and clean in lowercase_words:
                parts.append(clean)
            else:
                parts.append(clean[:1].upper() + clean[1:])
        words.append('-'.join(parts))
    return ' '.join(words)

def index(request):
	return redirect('/dashboard/v3')

def dashboardv1(request):
	return render(request, "pages/index.html")

def dashboardv2(request):
	return render(request, "pages/index-v2.html")

def dashboardv3(request):
	scope = user_scope(request)
	labels = {"local": "Acesso local", "municipal": "Acesso municipal", "regional": "Acesso regional", "global": "Acesso global"}
	location = scope.get('comum') if scope.get('level') == 'local' else scope.get('municipio') if scope.get('level') == 'municipal' else 'Regional Itapevi'
	return render(request, "pages/index-v3.html", {
		'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
		'access_scope_label': labels.get(scope.get('level'), 'Acesso local'),
		'access_scope_location': location or 'Escopo nao configurado',
	})



import requests
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import json

def log_audit(request, action, module='GLOBAL', details=None):
    """Utility to log user actions to the audit_logs table in Supabase."""
    url = f"{settings.SUPABASE_URL}/rest/v1/audit_logs"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json"
    }
    
    user_id = request.session.get('user_id')
    payload = {
        "user_id": user_id,
        "action": action,
        "module": module,
        "details": details or {},
        "ip_address": request.META.get('REMOTE_ADDR'),
        "user_agent": request.META.get('HTTP_USER_AGENT')
    }
    
    try:
        requests.post(url, headers=headers, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to log audit: {e}")


def update_profile_activity(profile, event):
    """Atualiza a mesma public.profiles usada pelo login."""
    user_id = (profile or {}).get('user_id')
    if not user_id or event not in ('login', 'logout'):
        return profile or {}
    counter_field = f'contador_{event}s'
    date_field = f'data_ultimo_{event}'
    now = datetime.now().astimezone().isoformat()
    updated = {
        counter_field: int((profile or {}).get(counter_field) or 0) + 1,
        date_field: now,
        'updated_at': now,
    }
    try:
        response = requests.patch(
            f"{settings.SUPABASE_URL}/rest/v1/profiles",
            headers={
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={"user_id": f"eq.{user_id}"}, json=updated, timeout=10,
        )
        if response.ok and response.json():
            return response.json()[0]
    except Exception as exc:
        print(f"Failed to update profile activity: {exc}")
    return {**(profile or {}), **updated}


def start_access_session(request, profile):
    """Abre uma sessão confiável de utilização para consulta administrativa."""
    payload = {
        "user_id": (profile or {}).get("user_id"),
        "status": "active",
        "details": {
            "ip_address": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT"),
            "module": "VISITAS",
            "comum": (profile or {}).get("comum"),
            "municipio": (profile or {}).get("municipio") or (profile or {}).get("cidade"),
        },
    }
    try:
        response = requests.post(
            f"{settings.SUPABASE_URL}/rest/v1/audit_access_sessions",
            headers={
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json", "Prefer": "return=representation",
            }, json=payload, timeout=10,
        )
        if response.ok and response.json():
            request.session["audit_access_session_id"] = response.json()[0].get("id")
    except Exception as exc:
        print(f"Failed to start audit access session: {exc}")


def close_access_session(request, reason="user_logout"):
    session_id = request.session.get("audit_access_session_id")
    if not session_id:
        return
    now = datetime.now().astimezone().isoformat()
    try:
        requests.patch(
            f"{settings.SUPABASE_URL}/rest/v1/audit_access_sessions",
            headers={
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            }, params={"id": f"eq.{session_id}"},
            json={"status": "logged_out", "ended_at": now, "last_activity_at": now, "logout_reason": reason}, timeout=10,
        )
    except Exception as exc:
        print(f"Failed to close audit access session: {exc}")

@csrf_exempt
def apiAuth(request):
    """Proxy for Supabase Auth and Profiles management."""
    action = request.GET.get('action')
    
    if request.method == 'POST':
        data = json.loads(request.body) if request.body else {}
        
        if action == 'login':
            if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
                return JsonResponse({
                    "error": "Serviço de autenticação não configurado. Contate o administrador."
                }, status=503)
            try:
                url = f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password"
                headers = {"apikey": settings.SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"}
                payload = {"email": data.get('email'), "password": data.get('password')}
                
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    res_data = response.json()
                    token = res_data.get('access_token')
                    user_data = res_data.get('user', {})
                    user_id = user_data.get('id')
                    
                    if not user_id:
                        return JsonResponse({"error": "Usuário não encontrado no Supabase."}, status=404)
                    
                    # Fetch profile
                    profile_url = f"{settings.SUPABASE_URL}/rest/v1/profiles?user_id=eq.{user_id}&select=*"
                    profile_headers = {
                        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
                    }
                    profile_res = requests.get(profile_url, headers=profile_headers, timeout=10)
                    
                    if profile_res.status_code != 200:
                        return JsonResponse({"error": "Erro ao buscar perfil no banco de dados."}, status=profile_res.status_code)
                    
                    profiles = profile_res.json()
                    if not profiles or len(profiles) == 0:
                        return JsonResponse({"error": "Perfil não encontrado. Contate o administrador."}, status=404)
                    
                    profile = profiles[0]

                    # Repara contas do fluxo antigo, nas quais a comum ficou
                    # somente nos metadados do Auth e não chegou ao perfil.
                    auth_metadata = user_data.get('user_metadata') or {}
                    profile_common = str(profile.get('comum') or auth_metadata.get('comum') or '').strip()
                    common_row = next(
                        (item for item in common_catalog() if str(item.get('comum') or '').strip() == profile_common),
                        None,
                    )
                    if common_row and int(profile.get('role_id') or 4) == 4:
                        municipality = str(common_row.get('cidade') or '').strip()
                        repair = {
                            'comum': profile_common,
                            'municipio': municipality,
                            'cidade': municipality,
                            'role_id': 4,
                            'role': 'Instrutor',
                            'sector': 'Visitas',
                        }
                        if any(str(profile.get(key) or '').strip() != str(value) for key, value in repair.items()):
                            repair_response = requests.patch(
                                f"{settings.SUPABASE_URL}/rest/v1/profiles",
                                headers={
                                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                                    "Content-Type": "application/json",
                                    "Prefer": "return=representation",
                                },
                                params={"user_id": f"eq.{user_id}"}, json=repair, timeout=10,
                            )
                            if repair_response.ok:
                                profile.update(repair)

                    # Check status
                    if profile.get('status') != 'approved':
                        request.session['user_id'] = user_id
                        log_audit(request, 'LOGIN_DENIED', 'AUTH', {
                            "email": data.get('email'), "reason": "profile_not_approved",
                            "status": profile.get('status')
                        })
                        request.session.pop('user_id', None)
                        return JsonResponse({"error": "Sua conta está aguardando aprovação."}, status=403)
                    
                    # Save to session
                    request.session['supabase_token'] = token
                    request.session['user_id'] = user_id
                    profile = update_profile_activity(profile, 'login')
                    profile['email'] = data.get('email')
                    request.session['user_profile'] = profile
                    start_access_session(request, profile)
                    
                    log_audit(request, 'LOGIN', 'AUTH', {
                        "email": data.get('email'), "role_id": profile.get('role_id'),
                        "comum": profile.get('comum'),
                        "municipio": profile.get('municipio') or profile.get('cidade')
                    })
                    return JsonResponse({"status": "ok", "user": profile})
                
                # Auth failure
                try:
                    err_msg = response.json().get('error_description') or response.json().get('msg') or "Credenciais inválidas."
                except:
                    err_msg = "Credenciais inválidas."
                log_audit(request, 'LOGIN_FAILED', 'AUTH', {
                    "email": data.get('email'), "reason": err_msg
                })
                return JsonResponse({"error": err_msg}, status=response.status_code)
                
            except requests.RequestException:
                return JsonResponse({
                    "error": "Não foi possível conectar ao serviço de autenticação. Tente novamente."
                }, status=502)
            except (ValueError, KeyError, TypeError):
                return JsonResponse({
                    "error": "O serviço de autenticação retornou uma resposta inválida."
                }, status=502)

        elif action == 'register':
            if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
                print("Registration failed: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not configured")
                return JsonResponse({
                    "error": "Serviço de cadastro não configurado. Contate o administrador."
                }, status=503)

            comum = str(data.get('comum') or '').strip()
            comum_row = next(
                (item for item in common_catalog() if str(item.get('comum') or '').strip() == comum),
                None,
            )
            if not comum_row:
                return JsonResponse({
                    "error": "Selecione uma comum válida na lista oficial."
                }, status=400)
            municipio = str(comum_row.get('cidade') or '').strip()
            # 1. Sign up
            url = f"{settings.SUPABASE_URL}/auth/v1/signup"
            headers = {"apikey": settings.SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"}
            payload = {
                "email": data.get('email'), 
                "password": data.get('password'),
                "data": {
                    "full_name": data.get('full_name'),
                    "comum": comum,
                    "municipio": municipio,
                    "cidade": municipio,
                    "role_id": 4,
                    "access_level": "local",
                    "cadastro_origem": "app_visitas_regional",
                    "cadastro_origem_label": "Aplicativo Regional de Visitas",
                    "cadastro_origem_setor_sugerido": "Visitas",
                    "cadastro_origem_rota": request.path,
                }
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=15)
            except requests.RequestException as exc:
                print(f"Registration Auth request failed: {type(exc).__name__}: {exc}")
                return JsonResponse({
                    "error": "Não foi possível conectar ao serviço de cadastro. Tente novamente."
                }, status=502)

            if response.status_code in [200, 201]:
                try:
                    res_data = response.json()
                except ValueError as exc:
                    print(f"Registration Auth returned invalid JSON: {exc}")
                    return JsonResponse({
                        "error": "O serviço de cadastro retornou uma resposta inválida. Tente novamente."
                    }, status=502)
                user_id = res_data.get('id') or (res_data.get('user') or {}).get('id')
                if user_id:
                    profile_payload = {
                        "user_id": user_id,
                        "full_name": str(data.get('full_name') or '').strip(),
                        "comum": comum,
                        "municipio": municipio,
                        "cidade": municipio,
                        "role_id": 4,
                        "role": "Instrutor",
                        "status": "pending",
                        "cadastro_origem": "app_visitas_regional",
                        "cadastro_origem_label": "Aplicativo Regional de Visitas",
                        "cadastro_origem_setor_sugerido": "Visitas",
                        "cadastro_origem_rota": request.path,
                        "cadastro_origem_url": request.build_absolute_uri(),
                        "sector": "Visitas",
                    }
                    try:
                        profile_response = requests.post(
                            f"{settings.SUPABASE_URL}/rest/v1/profiles?on_conflict=user_id",
                            headers={
                                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                                "Content-Type": "application/json",
                                "Prefer": "resolution=merge-duplicates,return=representation",
                            }, json=profile_payload, timeout=10,
                        )
                    except requests.RequestException as exc:
                        profile_response = None
                        print(f"Registration profile request failed for user {user_id}: {type(exc).__name__}: {exc}")

                    if profile_response is None or not profile_response.ok:
                        if profile_response is not None:
                            print(
                                f"Registration profile save failed for user {user_id}: "
                                f"HTTP {profile_response.status_code} - {profile_response.text[:1000]}"
                            )
                        # Compensa a criação no Auth para não deixar uma conta
                        # sem perfil, que bloquearia uma nova tentativa com o e-mail.
                        rollback_succeeded = False
                        try:
                            rollback_response = requests.delete(
                                f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                                headers={
                                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                                }, timeout=10,
                            )
                            if not rollback_response.ok:
                                print(
                                    f"Registration rollback failed for user {user_id}: "
                                    f"HTTP {rollback_response.status_code} - {rollback_response.text[:1000]}"
                                )
                            else:
                                rollback_succeeded = True
                        except requests.RequestException as exc:
                            print(f"Registration rollback request failed for user {user_id}: {type(exc).__name__}: {exc}")
                        if not rollback_succeeded:
                            return JsonResponse({
                                "error": "O cadastro ficou incompleto e exige revisão do administrador. Não tente novamente com o mesmo e-mail."
                            }, status=502)
                        return JsonResponse({
                            "error": "Não foi possível concluir o cadastro. Nenhuma conta foi mantida; tente novamente."
                        }, status=502)
                else:
                    return JsonResponse({
                        "error": "O serviço criou a conta sem retornar sua identificação. Contate o administrador."
                    }, status=502)
                
                # Note: The trigger on Supabase (handle_new_user_profile) will create the profile record.
                # We just need to make sure level 7 is 'Usuário'.
                
                log_audit(request, 'REGISTER', details={
                    "email": data.get('email'), "user_id": user_id,
                    "comum": comum, "municipio": municipio, "role_id": 4,
                })
                return JsonResponse({"status": "ok", "message": "Registro realizado. Aguarde aprovação do administrador."})
            
            try:
                auth_error = response.json()
                error_message = (
                    auth_error.get('error_description') or auth_error.get('msg')
                    or auth_error.get('message') or auth_error.get('error')
                )
            except (ValueError, AttributeError):
                error_message = None
            print(f"Registration Auth rejected request: HTTP {response.status_code} - {response.text[:1000]}")
            return JsonResponse({
                "error": error_message or "O serviço de cadastro recusou a solicitação."
            }, status=response.status_code)

        elif action == 'logout':
            profile = update_profile_activity(request.session.get('user_profile') or {}, 'logout')
            request.session['user_profile'] = profile
            close_access_session(request)
            log_audit(request, 'LOGOUT', 'AUTH', {
                "email": profile.get('email'), "role_id": profile.get('role_id'),
                "comum": profile.get('comum')
            })
            request.session.flush()
            return JsonResponse({"status": "ok"})

    elif request.method == 'GET':
        if action == 'profile':
            profile = request.session.get('user_profile')
            if profile:
                return JsonResponse(profile)
            return JsonResponse({"error": "Not authenticated"}, status=401)

    return JsonResponse({"error": "Invalid action or method"}, status=400)

@csrf_exempt
def apiVisitas(request):
    scope = user_scope(request)
    if request.method == 'GET':
        ano = request.GET.get('ano')
        mes = request.GET.get('mes')
        comum = (request.GET.get('comum') or '').strip()
        municipio = (request.GET.get('municipio') or '').strip()

        url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS}"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        params = [
            ("select", "*"),
            ("order", "referencia_ano.desc,referencia_mes.desc")
        ]
        
        if ano and ano != 'all':
            params.append(("referencia_ano", f"eq.{ano}"))
        if mes and mes != 'all':
            params.append(("referencia_mes", f"eq.{mes}"))
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code != 200:
                return JsonResponse({"error": "Supabase Error", "status": response.status_code, "details": response.text}, status=response.status_code)
            rows = filter_rows(scope, response.json())
            # Monthly reports store musicians as `gvmu`; `gve` is the dashboard alias.
            for row in rows:
                row['gve'] = int(row.get('gvmu') or 0)
            catalog = {str(item.get('comum') or '').strip(): str(item.get('cidade') or '').strip() for item in visible_commons(scope)}
            if municipio:
                if municipio not in set(catalog.values()):
                    return JsonResponse({"error": "Município fora do seu escopo de acesso."}, status=403)
                rows = [row for row in rows if (
                    str(row.get('municipio') or row.get('cidade') or '').strip() == municipio
                    or (
                        not str(row.get('municipio') or row.get('cidade') or '').strip()
                        and catalog.get(str(row.get('comum') or '').strip()) == municipio
                    )
                )]
            if comum and comum != 'all':
                if comum not in catalog:
                    return JsonResponse({"error": "Comum fora do seu escopo de acesso."}, status=403)
                rows = [row for row in rows if str(row.get('comum') or '').strip() == comum]
            return JsonResponse(rows, safe=False)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    elif request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            if 'gve' in data and 'gvmu' not in data:
                data['gvmu'] = data.pop('gve')
            if not can_access(scope, data):
                return JsonResponse({"error": "Localidade fora do seu escopo de acesso."}, status=403)
            # Garantir calculo do total se não enviado
            if 'total_visitas' not in data:
                data['total_visitas'] = int(data.get('gvi', 0)) + int(data.get('gvm', 0)) + int(data.get('gvmu', 0)) + int(data.get('rf', 0)) + int(data.get('re', 0))
            if 'total' not in data:
                data['total'] = data['total_visitas']
                
            url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS}"
            headers = {
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code in [200, 201]:
                log_audit(request, 'CREATE', 'VISITAS_LANCAMENTOS', {
                    "scope": scope_details(scope), "novo": response.json()
                })
                return JsonResponse(response.json(), safe=False)
            else:
                return JsonResponse({"error": "Supabase Save Error", "status": response.status_code, "details": response.text}, status=response.status_code)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
    return JsonResponse({"error": "Method not allowed"}, status=405)

def apiVisitasIrmandade(request):
    scope = user_scope(request)
    can_view_restricted_notes = int((scope.get("profile") or {}).get("role_id") or 99) <= 3

    def protect_restricted_notes(rows):
        if can_view_restricted_notes:
            return rows
        for row in rows:
            if isinstance(row, dict):
                row.pop("apontamentos_restritos", None)
        return rows
    url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if request.method == 'GET':
        comum = request.GET.get('comum')
        status = request.GET.get('status')

        if comum and comum != 'all':
            allowed_commons = {str(item.get('comum') or '').strip() for item in visible_commons(scope)}
            if comum.strip() not in allowed_commons:
                return JsonResponse({"error": "Comum fora do seu escopo de acesso."}, status=403)

        params = [("select", "*"), ("order", "nome.asc")]
        
        if comum and comum != 'all':
            params.append(("comum", f"eq.{comum}"))
        if status and status != 'all':
            params.append(("status", f"eq.{status}"))
        
        setor = request.GET.get('setor')
        if setor and setor != 'all':
            params.append(("setor", f"eq.{setor}"))

        try:
            if request.GET.get('export') == '1':
                rows = []
                page_size = 1000
                for start in range(0, 100000, page_size):
                    page_headers = {**headers, "Range": f"{start}-{start + page_size - 1}"}
                    response = requests.get(url, headers=page_headers, params=params, timeout=30)
                    if response.status_code not in {200, 206}:
                        return JsonResponse({"error": "Supabase Error", "details": response.text}, status=response.status_code)
                    page = response.json()
                    rows.extend(page)
                    if len(page) < page_size:
                        break
                return JsonResponse(protect_restricted_notes(filter_rows(scope, rows)), safe=False)

            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code != 200:
                return JsonResponse({"error": "Supabase Error", "details": response.text}, status=response.status_code)
            return JsonResponse(protect_restricted_notes(filter_rows(scope, response.json())), safe=False)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    elif request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            records = data if isinstance(data, list) else [data]
            if not records or len(records) > 500:
                return JsonResponse({"error": "Envie entre 1 e 500 registros por lote."}, status=400)
            nullable_fields = {
                "id_chefe_familia", "ultima_visita", "data_nascimento", "data_batismo",
                "data_inicio_ensaios", "data_culto_oficial", "data_oficializacao",
            }
            for item in records:
                if isinstance(item, dict):
                    if not can_view_restricted_notes:
                        item.pop("apontamentos_restritos", None)
                    for field in nullable_fields:
                        if field in item and (item[field] is None or str(item[field]).strip() == ""):
                            item[field] = None
            if isinstance(data, list):
                # O PostgREST exige as mesmas chaves em todos os objetos do lote.
                batch_fields = set().union(*(item.keys() for item in records if isinstance(item, dict)))
                for item in records:
                    if isinstance(item, dict):
                        for field in batch_fields:
                            item.setdefault(field, None)
            data = records if isinstance(data, list) else records[0]
            if any(not isinstance(item, dict) or not can_access(scope, item) for item in records):
                return JsonResponse({"error": "Comum fora do seu escopo de acesso."}, status=403)
            skipped = 0
            updated = 0
            if isinstance(data, list) and request.GET.get('smart') == '1':
                def identity(value):
                    normalized = unicodedata.normalize('NFKD', str(value or ''))
                    return ' '.join(''.join(char for char in normalized if not unicodedata.combining(char)).casefold().split())

                existing_by_key = {}
                for comum in sorted({str(item.get('comum') or '').strip() for item in records}):
                    lookup = requests.get(
                        url,
                        headers={**headers, "Range": "0-9999"},
                        params={"select": "id,nome,comum,preferencia_periodo_visita,classificacao_adicional,apontamentos_restritos", "comum": f"eq.{comum}"},
                        timeout=30,
                    )
                    if lookup.status_code not in {200, 206}:
                        return JsonResponse({"error": "Não foi possível comparar os cadastros existentes.", "details": lookup.text}, status=lookup.status_code)
                    existing_by_key.update({
                        (identity(row.get('comum')), identity(row.get('nome'))): row
                        for row in lookup.json()
                    })

                new_records = []
                seen_in_file = set()
                for item in records:
                    key = (identity(item.get('comum')), identity(item.get('nome')))
                    existing = existing_by_key.get(key)
                    if existing:
                        enrichment = {}
                        for field in ('preferencia_periodo_visita', 'classificacao_adicional', 'apontamentos_restritos'):
                            incoming = item.get(field)
                            if incoming and incoming != existing.get(field):
                                enrichment[field] = incoming
                        if enrichment and existing.get('id'):
                            update_response = requests.patch(
                                url,
                                headers=headers,
                                params={"id": f"eq.{existing['id']}"},
                                json=enrichment,
                                timeout=10,
                            )
                            if update_response.status_code not in {200, 201, 204}:
                                return JsonResponse({"error": "Não foi possível atualizar as preferências existentes.", "details": update_response.text}, status=update_response.status_code)
                            updated += 1
                            existing.update(enrichment)
                        else:
                            skipped += 1
                        continue
                    if key in seen_in_file:
                        skipped += 1
                        continue
                    seen_in_file.add(key)
                    new_records.append(item)
                records = new_records
                data = records
                if not records:
                    return JsonResponse({"created": 0, "updated": updated, "skipped": skipped, "smart_import": True})

            response = requests.post(url, headers=headers, json=data, timeout=30 if isinstance(data, list) else 10)
            if response.status_code in [200, 201]:
                log_audit(request, 'CREATE', 'VISITAS_IRMANDADE', {
                    "scope": scope_details(scope),
                    "quantidade": len(records), "atualizados_existentes": updated, "ignorados_existentes": skipped,
                    "novo": response.json() if not isinstance(data, list) else {"importacao_em_lote": True},
                })
                if isinstance(data, list) and request.GET.get('smart') == '1':
                    return JsonResponse({"created": len(records), "updated": updated, "skipped": skipped, "smart_import": True})
                return JsonResponse(response.json(), safe=False)
            else:
                return JsonResponse({"error": "Save Error", "details": response.text}, status=response.status_code)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    elif request.method == 'PATCH':
        import json
        try:
            id = request.GET.get('id')
            if not id:
                return JsonResponse({"error": "ID is required"}, status=400)
            
            data = json.loads(request.body)
            if not can_view_restricted_notes:
                data.pop("apontamentos_restritos", None)
            current = requests.get(url, headers=headers, params=[("id", f"eq.{id}"), ("select", "*")], timeout=10).json()
            if not current or not can_access(scope, current[0]) or not can_access(scope, {**current[0], **data}):
                return JsonResponse({"error": "Registro fora do seu escopo de acesso."}, status=403)
            # Evita ciclo conjugal (esposo e esposa apontando um para o outro).
            # Se o cônjuge selecionado já pertence ao núcleo do membro atual,
            # o membro atual é a referência/chefe e não deve apontar de volta.
            selected_head_id = str(data.get('id_chefe_familia') or '').strip()
            if selected_head_id and str(data.get('vinculo_tipo') or '').strip().casefold() in {'cônjuge', 'conjuge'}:
                selected_response = requests.get(
                    url, headers=headers,
                    params=[('id', f'eq.{selected_head_id}'), ('select', 'id,id_chefe_familia,vinculo_tipo')],
                    timeout=10,
                )
                if selected_response.status_code == 200:
                    selected_rows = selected_response.json()
                    if selected_rows and str(selected_rows[0].get('id_chefe_familia') or '') == str(id):
                        data['id_chefe_familia'] = None
                        data['vinculo_tipo'] = None
            params = [("id", f"eq.{id}")]
            
            response = requests.patch(url, headers=headers, params=params, json=data, timeout=10)
            if response.status_code in [200, 201, 204]:
                log_audit(request, 'UPDATE', 'VISITAS_IRMANDADE', {
                    "scope": scope_details(scope), "anterior": current[0],
                    "novo": response.json() if response.text else data
                })
                return JsonResponse(response.json() if response.text else {"status": "ok"}, safe=False)
            else:
                print(f"ERRO SUPABASE: {response.status_code} - {response.text}")
                return JsonResponse({"error": "Update Error", "details": response.text}, status=response.status_code)
        except Exception as e:
            import traceback
            print(f"ERRO INTERNO: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({"error": str(e)}, status=500)


    elif request.method == 'DELETE':
        id = request.GET.get('id')
        if not id:
            return JsonResponse({"error": "ID is required"}, status=400)
            
        params = [("id", f"eq.{id}")]
        
        try:
            current = requests.get(url, headers=headers, params=params + [("select", "*")], timeout=10).json()
            if not current or not can_access(scope, current[0]):
                return JsonResponse({"error": "Registro fora do seu escopo de acesso."}, status=403)
            response = requests.delete(url, headers=headers, params=params, timeout=10)
            if response.status_code in [200, 204]:
                log_audit(request, 'DELETE', 'VISITAS_IRMANDADE', {
                    "scope": scope_details(scope), "anterior": current[0]
                })
                return JsonResponse({"status": "deleted"})
            else:
                return JsonResponse({"error": "Delete Error", "details": response.text}, status=response.status_code)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

def apiVisitasComuns(request):
    if request.method == 'GET':
        try:
            return JsonResponse(visible_commons(user_scope(request)), safe=False)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Method not allowed"}, status=405)

def visitasDashboard(request):
    scope = user_scope(request)
    comuns = visible_commons(scope)
    comum_padrao = scope.get('comum') or ''
    comum_key = comum_padrao.strip().casefold()
    comum_row = next((row for row in comuns if str(row.get('comum') or '').strip().casefold() == comum_key), {})
    return render(request, "pages/visitas-dashboard.html", {
        'dashboard_access_level': scope.get('level'),
        'dashboard_comum_padrao': comum_padrao,
        'dashboard_municipio_padrao': comum_row.get('cidade') or scope.get('municipio') or '',
        'dashboard_comuns': comuns,
        'dashboard_municipios': sorted({row.get('cidade') for row in comuns if row.get('cidade')}),
    })

def visitasAnalytics(request):
    return render(request, "pages/visitas-analytics.html")

def visitasCadastro(request):
    scope = user_scope(request)
    comuns = visible_commons(scope)
    comum_padrao = scope.get('comum') or ''
    comum_row = next((row for row in comuns if row.get('comum') == comum_padrao), {})
    return render(request, "pages/visitas-cadastro.html", {
        'cadastro_access_level': scope.get('level'),
        'cadastro_comum_padrao': comum_padrao,
        'cadastro_municipio_padrao': comum_row.get('cidade') or scope.get('municipio') or '',
        'cadastro_comuns': comuns,
        'cadastro_municipios': sorted({row.get('cidade') for row in comuns if row.get('cidade')}),
        'cadastro_pode_ver_apontamentos': int((scope.get('profile') or {}).get('role_id') or 99) <= 3,
    })

def visitasAgenda(request):
    scope = user_scope(request)
    comuns = visible_commons(scope)
    comum_padrao = scope.get('comum') or ''
    comum_row = next((row for row in comuns if row.get('comum') == comum_padrao), {})
    return render(request, 'pages/visitas-agenda.html', {
        'agenda_access_level': scope.get('level'),
        'agenda_comum_padrao': comum_padrao,
        'agenda_municipio_padrao': comum_row.get('cidade') or scope.get('municipio') or '',
        'agenda_comuns': comuns,
        'agenda_municipios': sorted({row.get('cidade') for row in comuns if row.get('cidade')}),
    })


def visitasEquipes(request):
    scope = user_scope(request)
    comuns = visible_commons(scope)
    comum_padrao = scope.get('comum') or ''
    comum_row = next((row for row in comuns if row.get('comum') == comum_padrao), {})
    return render(request, 'pages/visitas-equipes.html', {
        'comuns': comuns,
        'municipios': sorted({row.get('cidade') for row in comuns if row.get('cidade')}),
        'comum_padrao': comum_padrao,
        'municipio_padrao': comum_row.get('cidade') or scope.get('municipio') or '',
    })


def visitasRelatoriosEquipes(request):
    scope = user_scope(request)
    comuns = visible_commons(scope)
    return render(request, 'pages/visitas-relatorios-equipes.html', {
        'comuns': comuns,
        'municipios': sorted({row.get('cidade') for row in comuns if row.get('cidade')}),
        'report_access_level': scope.get('level'),
        'municipio_padrao': scope.get('municipio') or '',
        'comum_padrao': scope.get('comum') or '',
    })


def apiVisitasRelatoriosEquipes(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método não permitido.'}, status=405)
    scope = user_scope(request)
    headers = {
        'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
        'Content-Type': 'application/json',
    }
    def fetch_all(url, params):
        rows = []
        page_size = 1000
        for offset in range(0, 1000000, page_size):
            response = requests.get(
                url, headers={**headers, 'Range': f'{offset}-{offset + page_size - 1}'},
                params=params, timeout=30,
            )
            response.raise_for_status()
            page = response.json()
            rows.extend(page)
            if len(page) < page_size:
                break
        return rows
    try:
        member_rows = fetch_all(
            f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}",
            {'select': 'id,comum'},
        )
        members = {str(row.get('id')): row for row in filter_rows(scope, member_rows)}
        agenda_params = [('select', '*'), ('order', 'data_inicio.desc')]
        start = (request.GET.get('inicio') or '').strip()
        end = (request.GET.get('fim') or '').strip()
        if start:
            agenda_params.append(('data_inicio', f'gte.{start}T00:00:00'))
        if end:
            agenda_params.append(('data_inicio', f'lte.{end}T23:59:59'))
        agenda_rows = fetch_all(
            f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_AGENDA}",
            agenda_params,
        )
        team_rows = fetch_all(
            f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_EQUIPES}",
            {'select': '*'},
        )
        teams = {str(row.get('id')): row for row in team_rows}
        catalog = {str(row.get('comum') or '').strip(): str(row.get('cidade') or '').strip() for row in visible_commons(scope)}
        selected_city = (request.GET.get('municipio') or '').strip()
        selected_common = (request.GET.get('comum') or '').strip()
        selected_type = (request.GET.get('tipo') or '').strip().upper()
        grouped = {}
        trend_grouped = {}
        for visit in agenda_rows:
            member = members.get(str(visit.get('irmandade_id') or ''))
            if not member:
                continue
            comum = str(member.get('comum') or '').strip()
            municipio = catalog.get(comum, '')
            team = teams.get(str(visit.get('equipe_id') or '')) or {}
            raw_name = team.get('nome') or visit.get('equipe_responsavel')
            team_type = team.get('tipo') or visit.get('equipe_tipo') or visit_team_type(raw_name)
            name = format_display_name(normalize_team_name(raw_name, team_type))
            if selected_city and municipio != selected_city:
                continue
            if selected_common and comum != selected_common:
                continue
            if selected_type in {'LOCAL', 'REGIONAL'} and team_type != selected_type:
                continue
            key = (team_type, municipio, comum if team_type == 'LOCAL' else '', name)
            row = grouped.setdefault(key, {
                'tipo': team_type, 'municipio': municipio,
                'comum': comum if team_type == 'LOCAL' else '', 'equipe': name,
                'total': 0, 'realizadas': 0, 'agendadas': 0, 'nao_realizadas': 0, 'canceladas': 0,
            })
            row['total'] += 1
            status = str(visit.get('status') or '').casefold()
            if status == 'realizada': row['realizadas'] += 1
            elif status == 'cancelada': row['canceladas'] += 1
            elif status in {'não realizada', 'nao realizada'}: row['nao_realizadas'] += 1
            else: row['agendadas'] += 1
            month = str(visit.get('data_inicio') or '')[:7]
            if re.fullmatch(r'\d{4}-\d{2}', month):
                trend_key = (team_type, month)
                trend = trend_grouped.setdefault(trend_key, {
                    'tipo': team_type, 'mes': month, 'total': 0, 'realizadas': 0,
                    'agendadas': 0, 'nao_realizadas': 0, 'canceladas': 0,
                })
                trend['total'] += 1
                if status == 'realizada': trend['realizadas'] += 1
                elif status == 'cancelada': trend['canceladas'] += 1
                elif status in {'não realizada', 'nao realizada'}: trend['nao_realizadas'] += 1
                else: trend['agendadas'] += 1
        def report_sort_key(row):
            regional_match = re.fullmatch(r'Grupo\s+([A-Z])', str(row.get('equipe') or ''), flags=re.IGNORECASE)
            team_order = regional_match.group(1).upper() if regional_match else str(row.get('equipe') or '').casefold()
            return (row['tipo'], row['municipio'], row['comum'], team_order)
        rows = sorted(grouped.values(), key=report_sort_key)
        trends = sorted(trend_grouped.values(), key=lambda item: (item['tipo'], item['mes']))
        return JsonResponse({'rows': rows, 'local': [r for r in rows if r['tipo'] == 'LOCAL'], 'regional': [r for r in rows if r['tipo'] == 'REGIONAL'], 'trends': trends})
    except requests.RequestException as exc:
        return JsonResponse({'error': 'Não foi possível gerar os relatórios.', 'details': str(exc)}, status=502)


def apiVisitasEquipes(request):
    """Atribui uma equipe aos membros já cadastrados em visitas_irmandade."""
    scope = user_scope(request)
    url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}"
    teams_url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_EQUIPES}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    def database_error(response):
        try:
            payload = response.json()
        except Exception:
            payload = {}
        if ('grupo_regional_id' in str(payload) or 'grupo_regional_nome' in str(payload)) and payload.get('code') in {'PGRST204', '42703'}:
            return JsonResponse({
                'error': 'O vínculo regional independente ainda não foi habilitado no banco.',
                'migration': 'scripts/migrations/007_visitas_duplo_vinculo_equipes.sql',
            }, status=503)
        if payload.get('code') in {'PGRST204', '42703'} or 'equipe_visita' in str(payload):
            return JsonResponse({
                'error': 'O campo de equipe ainda não foi criado no cadastro da irmandade.',
                'migration': 'scripts/migrations/001_visitas_equipes.sql',
            }, status=503)
        return JsonResponse({'error': payload.get('message') or response.text}, status=response.status_code)

    try:
        if request.method == 'GET':
            if request.GET.get('modo') == 'catalogo':
                response = requests.get(
                    teams_url, headers=headers,
                    params={'select': '*', 'order': 'municipio.asc,tipo.asc,comum.asc,nome.asc'}, timeout=15,
                )
                if response.status_code != 200:
                    return JsonResponse({
                        'error': 'A estrutura de equipes ainda não foi criada no banco.',
                        'migration': 'scripts/migrations/002_visitas_equipes_estruturadas.sql',
                        'details': response.text,
                    }, status=503)
                teams = filter_rows(scope, response.json())
                municipio = (request.GET.get('municipio') or '').strip()
                comum = (request.GET.get('comum') or '').strip()
                tipo = (request.GET.get('tipo') or '').strip().upper()
                if municipio:
                    teams = [item for item in teams if str(item.get('municipio') or '').strip() == municipio]
                if comum:
                    teams = [item for item in teams if not item.get('comum') or str(item.get('comum')).strip() == comum]
                if tipo in {'LOCAL', 'REGIONAL'}:
                    teams = [item for item in teams if item.get('tipo') == tipo]
                return JsonResponse(teams, safe=False)

            comum = (request.GET.get('comum') or '').strip()
            municipio = (request.GET.get('municipio') or '').strip()
            tipo = (request.GET.get('tipo') or '').strip().upper()
            params = {
                "select": "id,nome,comum,setor,status,cargo_outros,equipe_visita,equipe_id,grupo_regional_id,grupo_regional_nome",
                "order": "comum.asc,equipe_visita.asc,nome.asc",
            }
            # A listagem dos grupos regionais precisa enxergar participantes de
            # todas as comuns do município. A comum continua sendo usada quando
            # não há um filtro municipal (ex.: seleção no modal local).
            if comum and tipo != 'REGIONAL' and not municipio:
                params['comum'] = f'eq.{comum}'
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code != 200:
                return database_error(response)
            rows = filter_rows(scope, response.json())
            for row in rows:
                if row.get('equipe_visita'):
                    row['equipe_visita'] = normalize_visit_team(row['equipe_visita'])
                if row.get('grupo_regional_nome'):
                    row['grupo_regional_nome'] = normalize_team_name(row['grupo_regional_nome'], 'REGIONAL')
            if comum and tipo != 'REGIONAL' and not municipio:
                rows = [row for row in rows if str(row.get('comum') or '').strip() == comum]
            catalogo = {row.get('comum'): row.get('cidade') for row in visible_commons(scope)}
            if municipio:
                rows = [row for row in rows if str(catalogo.get(row.get('comum')) or '').strip() == municipio]
            if tipo == 'REGIONAL':
                rows = [row for row in rows if str(row.get('grupo_regional_id') or '').strip()]
            elif tipo == 'LOCAL':
                rows = [row for row in rows if str(row.get('equipe_id') or '').strip()]
            if request.GET.get('modo') == 'membros':
                busca = (request.GET.get('busca') or '').strip().casefold()
                listar_elegiveis = request.GET.get('elegiveis') == 'true'
                if busca or listar_elegiveis:
                    if listar_elegiveis:
                        rows = [row for row in rows if str(row.get('status') or 'Ativo').casefold() == 'ativo']
                    if busca:
                        rows = [row for row in rows if busca in str(row.get('nome') or '').casefold()]
                else:
                    rows = [row for row in rows if str(row.get('equipe_visita') or '').strip() or str(row.get('grupo_regional_nome') or '').strip()]
                return JsonResponse([{**row, 'municipio': catalogo.get(row.get('comum'), '')} for row in rows], safe=False)
            somente_atribuidos = request.GET.get('atribuidos') != 'false'
            if somente_atribuidos:
                rows = [row for row in rows if str(row.get('equipe_visita') or '').strip() or str(row.get('grupo_regional_nome') or '').strip()]
            grupos = {}
            for membro in rows:
                equipe = str(membro.get('equipe_visita') or '').strip()
                if not equipe:
                    continue
                chave = (membro.get('comum') or '', equipe)
                grupo = grupos.setdefault(chave, {
                    'id': f"{chave[0]}::{equipe}", 'nome': equipe, 'comum': chave[0],
                    'municipio': catalogo.get(chave[0], ''), 'ativo': True,
                    'integrantes': [], 'membros': [],
                })
                grupo['integrantes'].append(membro.get('nome') or '')
                grupo['membros'].append({'id': membro.get('id'), 'nome': membro.get('nome') or '', 'status': membro.get('status')})
            return JsonResponse(list(grupos.values()), safe=False)

        if request.method not in {'POST', 'PATCH', 'DELETE'}:
            return JsonResponse({'error': 'Método não permitido.'}, status=405)

        member_id = request.GET.get('id')
        team_delete_id = (request.GET.get('equipe_id') or '').strip()
        if request.method == 'DELETE' and team_delete_id:
            team_lookup = requests.get(
                teams_url, headers=headers,
                params={'id': f'eq.{team_delete_id}', 'select': '*'}, timeout=15,
            )
            if team_lookup.status_code != 200:
                return database_error(team_lookup)
            team_rows = team_lookup.json()
            if not team_rows:
                return JsonResponse({'error': 'Equipe não encontrada.'}, status=404)
            team = team_rows[0]
            if not can_access(scope, team):
                return JsonResponse({'error': 'Equipe fora do seu escopo de acesso.'}, status=403)
            regional = team.get('tipo') == 'REGIONAL'
            link_field = 'grupo_regional_id' if regional else 'equipe_id'
            clear_data = {'grupo_regional_id': None, 'grupo_regional_nome': None} if regional else {'equipe_id': None, 'equipe_visita': None}
            detach = requests.patch(url, headers=headers, params={link_field: f'eq.{team_delete_id}'}, json=clear_data, timeout=15)
            if detach.status_code not in {200, 201, 204}:
                return database_error(detach)
            deleted = requests.delete(teams_url, headers=headers, params={'id': f'eq.{team_delete_id}'}, timeout=15)
            if deleted.status_code not in {200, 204}:
                return database_error(deleted)
            log_audit(request, 'DELETE_TEAM', 'VISITAS_EQUIPES', {'anterior': team, 'scope': scope_details(scope)})
            return JsonResponse({'status': 'deleted'})
        current = []
        if request.method in {'PATCH', 'DELETE'}:
            if not member_id:
                return JsonResponse({'error': 'Membro não informado.'}, status=400)
            lookup = requests.get(url, headers=headers, params={'id': f'eq.{member_id}', 'select': '*'}, timeout=15)
            if lookup.status_code != 200:
                return database_error(lookup)
            current = lookup.json()
            if not current or not can_access(scope, current[0]):
                return JsonResponse({'error': 'Equipe fora do seu escopo de acesso.'}, status=403)

        if request.method == 'DELETE':
            regional = (request.GET.get('tipo') or '').strip().upper() == 'REGIONAL'
            clear_data = {'grupo_regional_id': None, 'grupo_regional_nome': None} if regional else {'equipe_id': None, 'equipe_visita': None}
            response = requests.patch(url, headers=headers, params={'id': f'eq.{member_id}'}, json=clear_data, timeout=15)
            if response.status_code not in {200, 201, 204}:
                return database_error(response)
            log_audit(request, 'REMOVE_TEAM_MEMBER', 'VISITAS_EQUIPES', {'anterior': current[0], 'scope': scope_details(scope)})
            return JsonResponse({'status': 'deleted'})

        data = json.loads(request.body or '{}')
        if data.get('acao') == 'cadastrar_equipe':
            team_type = str(data.get('tipo') or '').strip().upper()
            municipio = str(data.get('municipio') or '').strip()
            comum = str(data.get('comum') or '').strip() or None
            name = normalize_team_name(data.get('nome'), team_type)
            candidate = {'municipio': municipio, 'comum': comum}
            if team_type not in {'LOCAL', 'REGIONAL'} or not municipio or not name:
                return JsonResponse({'error': 'Informe tipo, nome e município da equipe.'}, status=400)
            if team_type == 'LOCAL':
                if not comum or not re.fullmatch(r'Equipe\s+\d+', name):
                    return JsonResponse({'error': 'Equipe local deve ter uma comum e nome numérico, como Equipe 1.'}, status=400)
            else:
                comum = None
                candidate['comum'] = None
                if not re.fullmatch(r'Grupo\s+[A-Z]', name):
                    return JsonResponse({'error': 'Grupo regional deve usar uma letra, como Grupo A.'}, status=400)
            if not can_access(scope, candidate):
                return JsonResponse({'error': 'Localidade fora do seu escopo de acesso.'}, status=403)
            payload = {'nome': name, 'tipo': team_type, 'municipio': municipio, 'comum': comum, 'ativo': True}
            response = requests.post(teams_url, headers=headers, json=payload, timeout=15)
            if response.status_code not in {200, 201}:
                message = 'Já existe uma equipe com esse nome nesta localidade.' if response.status_code == 409 else response.text
                return JsonResponse({'error': message}, status=response.status_code)
            result = response.json()
            log_audit(request, 'CREATE_TEAM', 'VISITAS_EQUIPES', {'novo': result, 'scope': scope_details(scope)})
            return JsonResponse(result, safe=False)

        member_id = str(data.get('membro_id') or member_id or '').strip()
        team_id = str(data.get('equipe_id') or '').strip()
        equipe = normalize_team_name(data.get('equipe'))
        if not member_id or not team_id:
            return JsonResponse({'error': 'Selecione o membro e uma equipe cadastrada.'}, status=400)
        if not current or str(current[0].get('id')) != member_id:
            lookup = requests.get(url, headers=headers, params={'id': f'eq.{member_id}', 'select': '*'}, timeout=15)
            if lookup.status_code != 200:
                return database_error(lookup)
            current = lookup.json()
        if not current or not can_access(scope, current[0]):
            return JsonResponse({'error': 'Membro fora do seu escopo de acesso.'}, status=403)
        team_response = requests.get(teams_url, headers=headers, params={'id': f'eq.{team_id}', 'select': '*'}, timeout=15)
        if team_response.status_code != 200 or not team_response.json():
            return JsonResponse({'error': 'Equipe não encontrada.'}, status=404)
        team = team_response.json()[0]
        if not can_access(scope, team):
            return JsonResponse({'error': 'Equipe fora do seu escopo de acesso.'}, status=403)
        member_common = str(current[0].get('comum') or '').strip()
        member_city = next((str(item.get('cidade') or '').strip() for item in visible_commons(scope) if str(item.get('comum') or '').strip() == member_common), '')
        if team.get('tipo') == 'LOCAL' and member_common != str(team.get('comum') or '').strip():
            return JsonResponse({'error': 'Equipe local aceita somente participantes da própria comum.'}, status=400)
        if team.get('tipo') == 'REGIONAL' and member_city != str(team.get('municipio') or '').strip():
            return JsonResponse({'error': 'Grupo regional aceita somente participantes do mesmo município.'}, status=400)
        equipe = normalize_team_name(team.get('nome'), team.get('tipo'))
        cargos = [cargo.strip() for cargo in str(current[0].get('cargo_outros') or '').split(',') if cargo.strip()]
        if not any(cargo.casefold() == 'grupo de visitas' for cargo in cargos):
            cargos.append('Grupo de Visitas')
        if team.get('tipo') == 'REGIONAL':
            update_data = {'grupo_regional_id': team_id, 'grupo_regional_nome': equipe, 'cargo_outros': ','.join(cargos)}
        else:
            update_data = {'equipe_id': team_id, 'equipe_visita': equipe, 'cargo_outros': ','.join(cargos)}
        response = requests.patch(url, headers=headers, params={'id': f'eq.{member_id}'}, json=update_data, timeout=15)
        if response.status_code not in {200, 201}:
            return database_error(response)
        result = response.json()
        log_audit(request, 'ASSIGN_TEAM_MEMBER', 'VISITAS_EQUIPES', {
            'anterior': current[0], 'membro_id': member_id, 'equipe': equipe, 'scope': scope_details(scope),
        })
        return JsonResponse(result, safe=False)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Dados inválidos.'}, status=400)
    except requests.RequestException as exc:
        return JsonResponse({'error': 'Falha ao acessar as equipes.', 'details': str(exc)}, status=502)

def visitasMapa(request):
    scope = user_scope(request)
    comuns = visible_commons(scope)
    context = {
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'map_access_level': scope.get('level'),
        'map_default_comum': scope.get('comum') or '',
        'map_default_municipio': scope.get('municipio') or '',
        'map_comuns': comuns,
        'map_municipios': sorted({item.get('cidade') for item in comuns if item.get('cidade')}),
    }
    return render(request, "pages/visitas-mapa.html", context)

def visitasRoteiroForm(request):
    scope = user_scope(request)
    comuns = visible_commons(scope)
    comum_padrao = scope.get("comum") or ""
    comum_row = next((item for item in comuns if item.get('comum') == comum_padrao), {})
    return render(request, "pages/visitas-roteiro-form.html", {
        "comuns": comuns,
        "municipios": sorted({item.get('cidade') for item in comuns if item.get('cidade')}),
        "comum_padrao": comum_padrao,
        "municipio_padrao": comum_row.get('cidade') or scope.get('municipio') or '',
    })


def visitasNavegar(request):
    """Página pública e segura para escolher o aplicativo de navegação do QR Code."""
    lat_raw = (request.GET.get('lat') or '').strip()
    lng_raw = (request.GET.get('lng') or '').strip()
    address = ' '.join((request.GET.get('endereco') or '').strip().split())[:300]
    title = ' '.join((request.GET.get('nome') or '').strip().split())[:100]
    destination = ''
    has_coordinates = False

    if lat_raw and lng_raw:
        try:
            lat = float(lat_raw.replace(',', '.'))
            lng = float(lng_raw.replace(',', '.'))
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
            destination = f'{lat:.7f},{lng:.7f}'
            has_coordinates = True
        except ValueError:
            destination = ''

    if not destination and address:
        destination = address

    context = {'title': title, 'address': address, 'has_destination': bool(destination)}
    if destination:
        waze_params = {'ll': destination, 'navigate': 'yes'} if has_coordinates else {'q': destination, 'navigate': 'yes'}
        context.update({
            'waze_url': f'https://waze.com/ul?{urlencode(waze_params)}',
            'google_maps_url': f'https://www.google.com/maps/dir/?{urlencode({"api": "1", "destination": destination})}',
        })
    return render(request, 'pages/visitas-navegar.html', context, status=200 if destination else 400)


def apiRoteiroBairros(request):
    """Lista bairros da comum ordenados pela proximidade do ponto central."""
    if request.method != "GET":
        return JsonResponse({"error": "Método não permitido."}, status=405)
    comum = (request.GET.get("comum") or "").strip()
    if not comum:
        return JsonResponse({"bairros": [], "error": "Selecione uma comum."}, status=400)
    scope = user_scope(request)
    comum_row = next((row for row in visible_commons(scope) if str(row.get("comum") or "").strip() == comum), None)
    if not comum_row:
        return JsonResponse({"error": "Comum fora do seu escopo de acesso."}, status=403)
    try:
        from .utils.routing import discover_nearby_neighborhoods
        bairros = discover_nearby_neighborhoods(
            comum, comum_row.get("cidade") or "", request.GET.get("data") or None
        )
        return JsonResponse({"bairros": bairros, "comum": comum, "cidade": comum_row.get("cidade") or ""})
    except Exception as exc:
        return JsonResponse({"error": "Não foi possível mapear os bairros.", "details": str(exc)}, status=502)

def visitasRoteiro(request):
    scope = user_scope(request)
    equipe = normalize_visit_team(request.GET.get('equipe'))
    data_filtro = request.GET.get('data') # formato YYYY-MM-DD
    comum = (request.GET.get('comum') or scope.get('comum') or '').strip()
    bairro = (request.GET.get('bairro') or '').strip()
    comum_row = next((row for row in visible_commons(scope) if str(row.get('comum') or '').strip() == comum), None)
    if comum and not comum_row:
        return render(request, 'pages/visitas-roteiro-impresso.html', {
            'error': 'A comum selecionada está fora do seu escopo de acesso.'
        })
    cidade_comum = (comum_row or {}).get('cidade') or ''
    
    # 1. Buscar Visitas da Agenda
    url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_AGENDA}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json"
    }
    
    params = [("select", "*")]
    if data_filtro:
        # Pega do inicio ao fim do dia
        params.append(("data_inicio", f"gte.{data_filtro}T00:00:00"))
        params.append(("data_inicio", f"lte.{data_filtro}T23:59:59"))
        
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        visitas = filter_rows(scope, response.json()) if response.status_code == 200 else []
        if equipe:
            visitas = [
                v for v in visitas
                if normalize_visit_team(v.get('equipe_responsavel')) == equipe
            ]
        
        # Filtrar apenas as que não estão canceladas/não realizadas
        visitas_validas = [v for v in visitas if v.get('status') not in ['Cancelada', 'Não realizada']]
        if bairro:
            visitas_validas = [
                v for v in visitas_validas
                if str(v.get('setor') or '').strip().casefold() == bairro.casefold()
            ]
        
        from .utils.routing import auto_dispatch_visits, clean_visit_address, get_common_coordinates, group_route_visits_by_address, limit_daily_route, optimize_route, order_route_chronologically
        
        # 2. Despacho Automático: a meta operacional é de 10 casas, não de
        # 10 pessoas. Moradores do mesmo endereço contam como uma única parada.
        total_casas = len(group_route_visits_by_address(visitas_validas))
        if total_casas < 10 and equipe and data_filtro:
            novas_visitas = auto_dispatch_visits(
                equipe, data_filtro, existing_visits=visitas_validas,
                comum=comum or None, cidade=cidade_comum, bairro=bairro or None,
            )
            if novas_visitas:
                visitas_validas.extend(filter_rows(scope, novas_visitas))

        # Completa o roteiro com os dados permanentes do cadastro. Esses campos
        # não pertencem ao agendamento e precisam acompanhar tanto visitas já
        # marcadas quanto as incluídas pelo despacho automático.
        member_ids = sorted({str(v.get('irmandade_id')) for v in visitas_validas if v.get('irmandade_id')})
        members_by_id = {}
        if member_ids:
            can_view_restricted_notes = int((scope.get('profile') or {}).get('role_id') or 99) <= 3
            member_fields = 'id,categoria,preferencia_periodo_visita'
            if can_view_restricted_notes:
                member_fields += ',apontamentos_restritos'
            member_response = requests.get(
                f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}",
                headers=headers,
                params={'select': member_fields, 'id': f"in.({','.join(member_ids)})"},
                timeout=10,
            )
            if member_response.status_code == 200:
                members_by_id = {str(item.get('id')): item for item in member_response.json()}
        for visit in visitas_validas:
            member = members_by_id.get(str(visit.get('irmandade_id'))) or {}
            visit['categoria'] = member.get('categoria') or visit.get('categoria') or 'GVI'
            visit['preferencia_periodo_visita'] = member.get('preferencia_periodo_visita') or ''
            if member.get('apontamentos_restritos'):
                visit['apontamentos_restritos'] = member['apontamentos_restritos']
                
        # 3. Ajustar fuso horário de volta para o Brasil (-3) no que veio do banco (UTC)
        from datetime import datetime, timezone, timedelta
        from dateutil import parser
        fuso_br = timezone(timedelta(hours=-3))
        
        for v in visitas_validas:
            if v.get('data_inicio'):
                try:
                    dt = parser.parse(v['data_inicio'])
                    if dt.tzinfo:
                        dt = dt.astimezone(fuso_br)
                    v['data_inicio'] = dt.strftime('%Y-%m-%dT%H:%M:%S')
                except:
                    pass
            if v.get('data_fim'):
                try:
                    dt = parser.parse(v['data_fim'])
                    if dt.tzinfo:
                        dt = dt.astimezone(fuso_br)
                    v['data_fim'] = dt.strftime('%Y-%m-%dT%H:%M:%S')
                except:
                    pass

        # Duas pessoas no mesmo endereço representam um único deslocamento neste
        # roteiro. A consolidação é somente visual e não altera os agendamentos.
        visitas_validas = group_route_visits_by_address(visitas_validas)
                    
        # 4. Separar manhã e tarde
        visitas_manha = []
        visitas_tarde = []
        for v in visitas_validas:
            hora = 12
            if v.get('data_inicio'):
                try:
                    hora = int(v['data_inicio'][11:13])
                except:
                    pass
            if hora < 12:
                visitas_manha.append(v)
            else:
                visitas_tarde.append(v)
                
        # 5. Otimizar Rota (separadamente)
        ponto_comum = get_common_coordinates(comum, cidade_comum) if comum else None
        roteiro_manha = order_route_chronologically(
            optimize_route(visitas_manha, start_coords=ponto_comum), start_coords=ponto_comum
        )
        roteiro_tarde = order_route_chronologically(
            optimize_route(visitas_tarde, start_coords=ponto_comum), start_coords=ponto_comum
        )
        # A referência operacional continua sendo 5 + 5, mas nenhuma visita já
        # programada pode desaparecer do documento quando houver excedente.
        roteiro_otimizado = limit_daily_route(roteiro_manha, roteiro_tarde)
        # O grupo parte uma única vez da congregação. Recalcula a sequência
        # completa para que a primeira distância seja desde o marco zero e todas
        # as demais partam da casa anterior, inclusive na troca de período.
        roteiro_otimizado = order_route_chronologically(
            roteiro_otimizado, start_coords=ponto_comum
        )
        selected_morning_count = len(roteiro_manha)
        for index, visit in enumerate(roteiro_otimizado, start=1):
            visit['route_number'] = index
            visit['route_period'] = 'manha' if index <= selected_morning_count else 'tarde'

        navigation_base_url = request.build_absolute_uri(reverse('ColorAdminApp:visitasNavegar'))
        for visit in roteiro_otimizado:
            visit['endereco_exibicao'] = clean_visit_address(visit.get('endereco_visitado'))
            if visit.get('lat') not in (None, '') and visit.get('lng') not in (None, ''):
                navigation_params = {'lat': visit['lat'], 'lng': visit['lng']}
            else:
                navigation_params = {'endereco': visit['endereco_exibicao']}
            visit['navigation_url'] = f'{navigation_base_url}?{urlencode(navigation_params)}'
            visit['qr_url'] = 'https://api.qrserver.com/v1/create-qr-code/?' + urlencode({
                'size': '180x180', 'data': visit['navigation_url']
            })
        
        data_br = data_filtro
        if data_filtro and len(data_filtro) == 10:
            data_br = f"{data_filtro[8:10]}/{data_filtro[5:7]}/{data_filtro[0:4]}"
        
        context = {
            'roteiro': roteiro_otimizado,
            'equipe': equipe,
            'data': data_br,
            'comum': comum,
            'bairro': bairro,
            'total_visitas_roteiro': len(roteiro_otimizado),
            'roteiro_excede_referencia': len(roteiro_otimizado) > 10,
        }
        return render(request, 'pages/visitas-roteiro-impresso.html', context)
    except Exception as e:
        print(f"Erro ao gerar roteiro: {e}")
        return render(request, 'pages/visitas-roteiro-impresso.html', {'error': str(e)})

def apiVisitasAgenda(request):
    scope = user_scope(request)
    url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_AGENDA}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    if request.method == 'GET':
        try:
            irmandade_id = request.GET.get('irmandade_id')
            status = request.GET.get('status')
            comum = (request.GET.get('comum') or '').strip()
            municipio = (request.GET.get('municipio') or '').strip()
            visible_catalog = visible_commons(scope)
            allowed_commons = {str(item.get('comum') or '').strip() for item in visible_catalog}
            allowed_municipios = {str(item.get('cidade') or '').strip() for item in visible_catalog}
            if comum:
                if comum not in allowed_commons:
                    return JsonResponse({"error": "Comum fora do seu escopo de acesso."}, status=403)
            if municipio and municipio not in allowed_municipios:
                return JsonResponse({"error": "Município fora do seu escopo de acesso."}, status=403)
            
            params = [("select", "*"), ("order", "data_inicio.asc")]
            if irmandade_id:
                params.append(("irmandade_id", f"eq.{irmandade_id}")) # ID do membro
            if status:
                params.append(("status", f"eq.{status}")) # Ex: Realizada
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            if start_date:
                params.append(("data_inicio", f"gte.{start_date}"))
            if end_date:
                params.append(("data_inicio", f"lt.{end_date}"))
                
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            rows = response.json()
            for row in rows:
                if row.get('equipe_responsavel'):
                    row['equipe_tipo'] = str(row.get('equipe_tipo') or visit_team_type(row['equipe_responsavel'])).upper()
                    row['equipe_responsavel'] = normalize_team_name(row['equipe_responsavel'], row['equipe_tipo'])
                notes_without_times, visit_times = split_visit_time_metadata(row.get('observacoes'))
                visible_notes, planned_period = split_visit_period_metadata(notes_without_times)
                row['observacoes'] = visible_notes
                row['periodo_planejado'] = planned_period
                row['horario_inicio'] = visit_times.get('inicio') or None
                row['horario_fim'] = visit_times.get('fim') or None
                row['duracao_minutos'] = visit_duration_minutes(visit_times)
                apply_actual_visit_times(row, visit_times)

            # A agenda se vincula territorialmente pelo UUID da irmandade. Filtrar
            # diretamente pela coluna `comum` deixava registros antigos invisiveis,
            # pois essa coluna nem sempre existe/esta preenchida na agenda.
            members_url = (
                f"{settings.SUPABASE_URL}/rest/v1/"
                f"{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}"
            )
            target_commons = {comum} if comum else {
                str(item.get('comum') or '').strip() for item in visible_catalog
                if not municipio or str(item.get('cidade') or '').strip() == municipio
            }
            common_cities = {
                str(item.get('comum') or '').strip(): str(item.get('cidade') or '').strip()
                for item in visible_catalog
            }
            member_locations = {}
            scoped_members = []
            offset = 0
            page_size = 1000
            while True:
                page_headers = {**headers, "Range": f"{offset}-{offset + page_size - 1}"}
                members_response = requests.get(
                    members_url,
                    headers=page_headers,
                    params=[("select", "id,comum,nome,endereco")],
                    timeout=15,
                )
                members_response.raise_for_status()
                member_page = members_response.json()
                for item in member_page:
                    member_common = str(item.get('comum') or '').strip()
                    if item.get('id') and member_common in target_commons:
                        member_locations[str(item['id'])] = member_common
                        scoped_members.append(item)
                if len(member_page) < page_size:
                    break
                offset += page_size

            hydrated_rows = []
            repaired_links = []
            for row in rows:
                row_member_id = str(row.get('irmandade_id') or '')
                if row_member_id not in member_locations:
                    orphan_member_id = row_member_id
                    matched_member = unique_member_for_orphan_visit(row, scoped_members)
                    if matched_member:
                        repair_response = requests.patch(
                            url,
                            headers=headers,
                            params=[('id', f"eq.{row.get('id')}")],
                            json={'irmandade_id': matched_member['id']},
                            timeout=10,
                        )
                        if repair_response.status_code in {200, 201, 204}:
                            row['irmandade_id'] = matched_member['id']
                            row_member_id = str(matched_member['id'])
                            repaired_links.append({
                                'agenda_id': row.get('id'),
                                'irmandade_id_anterior': orphan_member_id,
                                'irmandade_id_novo': matched_member['id'],
                            })
                row_common = member_locations.get(
                    row_member_id,
                    str(row.get('comum') or '').strip(),
                )
                if row_common not in target_commons:
                    continue
                row['comum'] = row_common
                row['municipio'] = common_cities.get(row_common, '')
                hydrated_rows.append(row)
            rows = filter_rows(scope, hydrated_rows)

            if repaired_links:
                log_audit(request, 'RECONCILE', 'VISITAS_AGENDA', {
                    'scope': scope_details(scope),
                    'vinculos_reparados': repaired_links,
                })

            return JsonResponse(rows, safe=False)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    elif request.method == 'POST' or request.method == 'PATCH':
        import json
        try:
            id = request.GET.get('id') if request.method == 'PATCH' else None
            data = json.loads(request.body)
            if 'equipe_responsavel' in data:
                data['equipe_responsavel'] = normalize_team_name(data['equipe_responsavel'], data.get('equipe_tipo'))
            current = []
            if id:
                current = requests.get(url, headers=headers, params=[("id", f"eq.{id}"), ("select", "*")], timeout=10).json()
                if current and 'observacoes' in data:
                    current_notes, current_times = split_visit_time_metadata(current[0].get('observacoes'))
                    _, current_period = split_visit_period_metadata(current_notes)
                    if current_period:
                        data['observacoes'] = merge_visit_period_metadata(data.get('observacoes'), current_period)
                    if current_times:
                        data['observacoes'] = merge_visit_time_metadata(data.get('observacoes'), current_times)
            candidate = {**(current[0] if current else {}), **data}
            if (id and not current) or not can_access(scope, candidate):
                return JsonResponse({"error": "Agenda fora do seu escopo de acesso."}, status=403)

            # Reserva territorial também para criações e edições manuais.
            # Esta regra também vale para lançamentos retroativos e é separada
            # da reserva territorial usada para organizar a agenda futura.
            candidate_team = normalize_team_name(
                candidate.get('equipe_responsavel'),
                candidate.get('equipe_tipo'),
            )
            if not candidate_team:
                return JsonResponse({
                    "error": "Selecione a equipe responsável pela visita."
                }, status=400)

            candidate_member = str(candidate.get('irmandade_id') or '').strip()
            candidate_start = str(candidate.get('data_inicio') or '').strip()
            if candidate_member and candidate_start:
                duplicate_response = requests.get(url, headers=headers, params=[
                    ("select", "id,status"),
                    ("irmandade_id", f"eq.{candidate_member}"),
                    ("data_inicio", f"eq.{candidate_start}"),
                ], timeout=10)
                if duplicate_response.status_code == 200:
                    duplicate = next((
                        item for item in duplicate_response.json()
                        if str(item.get('id')) != str(id or '')
                        and item.get('status') != 'Cancelada'
                    ), None)
                    if duplicate:
                        return JsonResponse({
                            "error": "Esta pessoa já possui uma visita registrada nesta data e horário."
                        }, status=409)

            candidate_day = str(candidate.get('data_inicio') or '')[:10]
            candidate_sector = str(candidate.get('setor') or '').strip()
            candidate_team = normalize_team_name(candidate.get('equipe_responsavel'), candidate.get('equipe_tipo'))
            # A reserva territorial organiza a agenda futura. Registros históricos
            # já concluídos não devem ser rejeitados por uma escala planejada para
            # outra equipe no mesmo bairro e dia.
            is_scheduled_visit = candidate.get('status') == 'Marcada'
            if is_scheduled_visit and candidate_day and candidate_sector and candidate_team:
                day_visits_response = requests.get(url, headers=headers, params=[
                    ("select", "id,setor,equipe_responsavel,equipe_tipo,status"),
                    ("data_inicio", f"gte.{candidate_day}T00:00:00"),
                    ("data_inicio", f"lte.{candidate_day}T23:59:59"),
                ], timeout=10)
                if day_visits_response.status_code == 200:
                    from .utils.routing import normalize_text
                    conflicting_team = next((
                        normalize_team_name(item.get('equipe_responsavel'), item.get('equipe_tipo')) for item in day_visits_response.json()
                        if str(item.get('id')) != str(id or '')
                        and item.get('status') != 'Cancelada'
                        and normalize_text(item.get('setor')) == normalize_text(candidate_sector)
                        and normalize_team_name(item.get('equipe_responsavel'), item.get('equipe_tipo')) != candidate_team
                    ), None)
                    if conflicting_team:
                        return JsonResponse({
                            "error": (
                                f"O bairro {candidate_sector} já está reservado para {conflicting_team} "
                                f"em {candidate_day}. Mantenha todo o bairro com a mesma equipe."
                            )
                        }, status=409)
            
            # Validação profissional: Se cancelada ou não realizada, exige motivo
            status_visita = data.get('status')
            if status_visita in ['Cancelada', 'Não realizada'] and not data.get('motivo_cancelamento'):
                return JsonResponse({"error": "Justificativa obrigatória para visitas canceladas ou não realizadas."}, status=400)

            if request.method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=10)
            else:
                response = requests.patch(url, headers=headers, params=[("id", f"eq.{id}")], json=data, timeout=10)
            
            if response.status_code in [200, 201, 204]:
                log_audit(request, 'CREATE' if request.method == 'POST' else 'UPDATE', 'VISITAS_AGENDA', {
                    "scope": scope_details(scope), "anterior": current[0] if current else None,
                    "novo": response.json() if response.text else data
                })
                return JsonResponse(response.json() if response.text else {"status": "ok"}, safe=False)
            
            try:
                err_content = response.json()
                msg = err_content.get('message', response.text)
                return JsonResponse({"error": msg}, status=response.status_code)
            except:
                return JsonResponse({"error": response.text}, status=response.status_code)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    elif request.method == 'DELETE':
        id = request.GET.get('id')
        try:
            import json
            body = json.loads(request.body or b'{}')
            ids = body.get('ids') if isinstance(body, dict) else None
            ids = [str(item).strip() for item in ids] if isinstance(ids, list) else ([str(id).strip()] if id else [])
            ids = list(dict.fromkeys(item for item in ids if item))
            if not ids:
                return JsonResponse({"error": "Selecione ao menos uma visita."}, status=400)
            if len(ids) > 500:
                return JsonResponse({"error": "Selecione no máximo 500 visitas por vez."}, status=400)
            try:
                from uuid import UUID
                ids = [str(UUID(item)) for item in ids]
            except (ValueError, TypeError, AttributeError):
                return JsonResponse({"error": "A seleção contém uma visita inválida."}, status=400)
            id_filter = f"in.({','.join(ids)})"
            current_response = requests.get(url, headers=headers, params=[("id", id_filter), ("select", "*")], timeout=15)
            current_response.raise_for_status()
            current = current_response.json()
            if len(current) != len(ids) or any(not can_access(scope, item) for item in current):
                return JsonResponse({"error": "Agenda fora do seu escopo de acesso."}, status=403)
            response = requests.delete(url, headers=headers, params=[("id", id_filter)], timeout=15)
            response.raise_for_status()
            log_audit(request, 'DELETE', 'VISITAS_AGENDA', {
                "scope": scope_details(scope), "anterior": current, "total": len(current)
            })
            return JsonResponse({"status": "deleted", "deleted": len(current)}, safe=False)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def apiGeocode(request):
    if request.method in {'GET', 'POST'}:
        try:
            data = json.loads(request.body or '{}') if request.method == 'POST' else request.GET
            address = data.get('address')

            if not address:
                return JsonResponse({'error': 'Address is required'}, status=400)

            from .utils.routing import geocode_address_fallback
            coordinates = geocode_address_fallback(address)
            if coordinates:
                return JsonResponse({
                    'lat': coordinates[0],
                    'lng': coordinates[1],
                    'formatted_address': address,
                    'source': 'google-or-arcgis',
                })
            return JsonResponse({'error': 'Não foi possível localizar o endereço.'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)
def apiStorageUpload(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    if not request.FILES.get('file'):
        return JsonResponse({"error": "No file uploaded"}, status=400)
    
    file = request.FILES['file']
    file_name = request.POST.get('name', file.name)
    # Ensure a safe filename or use UUID
    import uuid
    import os
    ext = os.path.splitext(file_name)[1]
    safe_name = f"{uuid.uuid4()}{ext}"
    
    bucket = "irmandade_fotos"
    url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{safe_name}"
    
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": file.content_type
    }
    
    def upload_to_supabase(content, current_url, current_headers):
        return requests.post(current_url, headers=current_headers, data=content, timeout=30)

    try:
        # Step 1: Upload the file
        print(f"--- INICIO DEBUG UPLOAD ---")
        file_content = file.read()
        response = upload_to_supabase(file_content, url, headers)
        
        # Se falhar porque o bucket não existe (404 ou 400 com mensagem específica)
        if response.status_code in [400, 404] and ("not found" in response.text.lower() or "not_found" in response.text.lower()):
            print(f"DEBUG: Bucket '{bucket}' não encontrado. Tentando criar automaticamente...")
            
            create_bucket_url = f"{settings.SUPABASE_URL}/storage/v1/bucket"
            create_headers = {
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json"
            }
            create_data = {
                "id": bucket,
                "name": bucket,
                "public": True
            }
            
            create_res = requests.post(create_bucket_url, headers=create_headers, json=create_data, timeout=10)
            print(f"DEBUG: Tentativa de criação do bucket: {create_res.status_code} - {create_res.text}")
            
            if create_res.status_code in [200, 201]:
                print(f"DEBUG: Bucket criado com sucesso! Repetindo upload...")
                response = upload_to_supabase(file_content, url, headers)

        print(f"--- FIM DEBUG UPLOAD --- Status: {response.status_code} | Resposta: {response.text}")
        
        if response.status_code in [200, 201]:
            # Step 2: Get public URL
            public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{safe_name}"
            return JsonResponse({"url": public_url, "name": safe_name}, status=200)
        else:
            # Tentar identificar o erro amigável
            try:
                err_json = response.json()
                msg = err_json.get('message') or err_json.get('error') or response.text
                if "Bucket not found" in msg:
                    msg = f"O bucket '{bucket}' não foi localizado no Storage. Por favor, crie um bucket chamado 'irmandade_fotos' manualmente no menu Storage do Supabase e marque como 'Public'."
            except:
                msg = response.text
                
            return JsonResponse({
                "error": "Falha no Supabase Storage", 
                "status": response.status_code, 
                "details": msg or "Erro interno do Supabase"
            }, status=400)
            
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def aiChat(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "p-0 d-flex position-relative bg-body"
	}
	return render(request, "pages/ai-chat.html", context)

def aiImageGenerator(request):
	return render(request, "pages/ai-image-generator.html")

def emailInbox(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/email-inbox.html", context)

def emailDetail(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/email-detail.html", context)

def emailCompose(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/email-compose.html", context)

def widgets(request):
	return render(request, "pages/widgets.html")

def uiGeneral(request):
	return render(request, "pages/ui-general.html")

def uiTypography(request):
	return render(request, "pages/ui-typography.html")

def uiTabsAccordions(request):
	return render(request, "pages/ui-tabs-accordions.html")

def uiUnlimitedNavTabs(request):
	return render(request, "pages/ui-unlimited-nav-tabs.html")

def uiModalNotifications(request):
	return render(request, "pages/ui-modal-notifications.html")

def uiWidgetBoxes(request):
	return render(request, "pages/ui-widget-boxes.html")

def uiMediaObject(request):
	return render(request, "pages/ui-media-object.html")

def uiButtons(request):
	return render(request, "pages/ui-buttons.html")

def uiIconFontawesome(request):
	return render(request, "pages/ui-icon-fontawesome.html")

def uiIconBootstrapIcons(request):
	return render(request, "pages/ui-icon-bootstrap-icons.html")

def uiIconDuotone(request):
	return render(request, "pages/ui-icon-duotone.html")

def uiIconSimpleLineIcons(request):
	return render(request, "pages/ui-icon-simple-line-icons.html")

def uiIconIonicons(request):
	return render(request, "pages/ui-icon-ionicons.html")

def uiTreeView(request):
	return render(request, "pages/ui-tree-view.html")

def uiLanguageBarIcon(request):
	context = {
		"appHeaderLanguageBar": 1
	}
	return render(request, "pages/ui-language-bar-icon.html", context)

def uiSocialButtons(request):
	return render(request, "pages/ui-social-buttons.html")

def uiIntroJS(request):
	return render(request, "pages/ui-intro-js.html")

def uiOffcanvasToasts(request):
	return render(request, "pages/ui-offcanvas-toasts.html")
	
def bootstrap5(request):
	return render(request, "pages/bootstrap-5.html")

def formElements(request):
	return render(request, "pages/form-elements.html")

def formPlugins(request):
	return render(request, "pages/form-plugins.html")

def formSliderSwitcher(request):
	return render(request, "pages/form-slider-switcher.html")
	
def formValidation(request):
	return render(request, "pages/form-validation.html")

def formWizards(request):
	return render(request, "pages/form-wizards.html")
	
def formWysiwyg(request):
	return render(request, "pages/form-wysiwyg.html")
	
def formXEditable(request):
	return render(request, "pages/form-x-editable.html")
	
def formMultipleFileUpload(request):
	return render(request, "pages/form-multiple-file-upload.html")
	
def formSummernote(request):
	return render(request, "pages/form-summernote.html")
	
def formDropzone(request):
	return render(request, "pages/form-dropzone.html")

def tableBasic(request):
	return render(request, "pages/table-basic.html")

def tableManageDefault(request):
	return render(request, "pages/table-manage-default.html")

def tableManageButtons(request):
	return render(request, "pages/table-manage-buttons.html")

def tableManageColReorder(request):
	return render(request, "pages/table-manage-col-reorder.html")

def tableManageFixedColumn(request):
	return render(request, "pages/table-manage-fixed-column.html")

def tableManageFixedHeader(request):
	return render(request, "pages/table-manage-fixed-header.html")

def tableManageKeytable(request):
	return render(request, "pages/table-manage-keytable.html")

def tableManageResponsive(request):
	return render(request, "pages/table-manage-responsive.html")

def tableManageRowReorder(request):
	return render(request, "pages/table-manage-row-reorder.html")

def tableManageScroller(request):
	return render(request, "pages/table-manage-scroller.html")

def tableManageSelect(request):
	return render(request, "pages/table-manage-select.html")

def tableManageExtensionCombination(request):
	return render(request, "pages/table-manage-extension-combination.html")

def posCustomerOrder(request):
	context = {
		"appSidebarHide": 1, 
		"appHeaderHide": 1,  
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/pos-customer-order.html", context)

def posKitchenOrder(request):
	context = {
		"appSidebarHide": 1, 
		"appHeaderHide": 1,  
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/pos-kitchen-order.html", context)

def posCounterCheckout(request):
	context = {
		"appSidebarHide": 1, 
		"appHeaderHide": 1,  
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/pos-counter-checkout.html", context)

def posTableBooking(request):
	context = {
		"appSidebarHide": 1, 
		"appHeaderHide": 1,  
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/pos-table-booking.html", context)

def posMenuStock(request):
	context = {
		"appSidebarHide": 1, 
		"appHeaderHide": 1,  
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/pos-menu-stock.html", context)

def chartFlot(request):
	return render(request, "pages/chart-flot.html")

def chartJs(request):
	return render(request, "pages/chart-js.html")

def chartD3(request):
	return render(request, "pages/chart-d3.html")

def chartApex(request):
	return render(request, "pages/chart-apex.html")
	
def landing(request):
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/landing.html", context)

def calendar(request):
	return render(request, "pages/calendar.html")

@csrf_exempt
def api_calendar_events(request):
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    if request.method == "GET":
        start = request.GET.get('start')
        end = request.GET.get('end')
        
        url = f"{settings.SUPABASE_URL}/rest/v1/visitas_agenda?select=*"
        if start and end:
            url += f"&and=(data_inicio.gte.{start},data_inicio.lt.{end})"
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            events = []
            for item in response.json():
                color = '#3b82f6'
                if item.get('categoria') == 'GVI': color = '#10b981'
                elif item.get('categoria') == 'GVM': color = '#f59e0b'
                elif item.get('categoria') == 'RF': color = '#8b5cf6'
                elif item.get('categoria') == 'RE': color = '#ec4899'
                elif item.get('categoria') == 'Músicos': color = '#14b8a6'
                
                events.append({
                    "id": item.get('id'),
                    "title": item.get('titulo') or "Visita",
                    "start": item.get('data_inicio'),
                    "end": item.get('data_fim') or item.get('data_inicio'),
                    "color": color,
                    "extendedProps": {
                        "categoria": item.get('categoria'),
                        "status": item.get('status'),
                        "observacoes": item.get('observacoes')
                    }
                })
            return JsonResponse(events, safe=False)
        return JsonResponse({"error": "Falha ao buscar visitas"}, status=500)

    elif request.method == "POST":
        data = json.loads(request.body)
        event_id = data.get('id')
        categoria = data.get('categoria')
        titulo = data.get('title') or f"Visita {categoria}"
        start = data.get('start')
        end = data.get('end') or start
        observacoes = data.get('observacoes')
        
        payload = {
            "titulo": titulo,
            "categoria": categoria,
            "data_inicio": start,
            "data_fim": end,
            "observacoes": observacoes
        }
        
        if event_id:
            url = f"{settings.SUPABASE_URL}/rest/v1/visitas_agenda?id=eq.{event_id}"
            res = requests.patch(url, headers=headers, json=payload)
            action = 'UPDATE_VISITA'
        else:
            url = f"{settings.SUPABASE_URL}/rest/v1/visitas_agenda"
            res = requests.post(url, headers=headers, json=payload)
            action = 'CREATE_VISITA'
            
        if res.status_code in [200, 201]:
            log_audit(request, action, module='CALENDAR', details=f"Visita: {titulo}")
            return JsonResponse({"success": True})
            
        return JsonResponse({"error": "Erro ao salvar visita"}, status=400)

def mapVector(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "p-0 position-relative"
	}
	return render(request, "pages/map-vector.html", context)

def mapGoogle(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "p-0 position-relative"
	}
	return render(request, "pages/map-google.html", context)

def galleryV1(request):
	return render(request, "pages/gallery-v1.html")

def galleryV2(request):
	return render(request, "pages/gallery-v2.html")

def pageOptionBlank(request):
	return render(request, "pages/page-option-blank.html")

def pageOptionWithFooter(request):
	return render(request, "pages/page-option-with-footer.html")

def pageOptionWithFixedFooter(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "d-flex flex-column p-0"
	}
	return render(request, "pages/page-option-with-fixed-footer.html", context)

def pageOptionWithoutSidebar(request):
	context = {
		"appSidebarHide": 1
	}
	return render(request, "pages/page-option-without-sidebar.html", context)

def pageOptionWithRightSidebar(request):
	context = {
		"appSidebarEnd": 1
	}
	return render(request, "pages/page-option-with-right-sidebar.html", context)

def pageOptionWithMinifiedSidebar(request):
	context = {
		"appSidebarMinified": 1
	}
	return render(request, "pages/page-option-with-minified-sidebar.html", context)

def pageOptionWithTwoSidebar(request):
	context = {
		"appSidebarTwo": 1,
		"appSidebarEndToggled": 1
	}
	return render(request, "pages/page-option-with-two-sidebar.html", context)

def pageOptionFullHeight(request):
	context = {
		"appContentFullHeight": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/page-option-full-height.html", context)

def pageOptionWithWideSidebar(request):
	context = {
		"appSidebarWide": 1
	}
	return render(request, "pages/page-option-with-wide-sidebar.html", context)

def pageOptionWithLightSidebar(request):
	context = {
		"appSidebarLight": 1
	}
	return render(request, "pages/page-option-with-light-sidebar.html", context)

def pageOptionWithMegaMenu(request):
	context = {
		"appHeaderMegaMenu": 1
	}
	return render(request, "pages/page-option-with-mega-menu.html", context)

def pageOptionWithTopMenu(request):
	context = {
		"appTopMenu": 1,
		"appSidebarHide": 1
	}
	return render(request, "pages/page-option-with-top-menu.html", context)

def pageOptionWithBoxedLayout(request):
	context = {
		"appBoxedLayout": 1
	}
	return render(request, "pages/page-option-with-boxed-layout.html", context)

def pageOptionWithMixedMenu(request):
	context = {
		"appTopMenu": 1
	}
	return render(request, "pages/page-option-with-mixed-menu.html", context)

def pageOptionBoxedLayoutWithMixedMenu(request):
	context = {
		"appBoxedLayout": 1,
		"appTopMenu": 1
	}
	return render(request, "pages/page-option-boxed-layout-with-mixed-menu.html", context)

def pageOptionWithTransparentSidebar(request):
	context = {
		"appSidebarTransparent": 1
	}
	return render(request, "pages/page-option-with-transparent-sidebar.html", context)

def pageOptionWithSearchSidebar(request):
	context = {
		"appSidebarSearch": 1
	}
	return render(request, "pages/page-option-with-search-sidebar.html", context)

def pageOptionWithHoverSidebar(request):
	context = {
		"appSidebarHover": 1
	}
	return render(request, "pages/page-option-with-hover-sidebar.html", context)

def extraTimeline(request):
	return render(request, "pages/extra-timeline.html")

def extraComingSoon(request):
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/extra-coming-soon.html", context)

def extraSearch(request):
	return render(request, "pages/extra-search.html")

def extraInvoice(request):
	return render(request, "pages/extra-invoice.html")

def extraError(request):
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/extra-error.html", context)

def extraProfile(request):
	context = {
		"appContentClass": "p-0"
	}
	return render(request, "pages/extra-profile.html", context)

def extraScrumBoard(request):
	context = {
		"appContentClass": "p-0",
		"appContentFullHeight": 1
	}
	return render(request, "pages/extra-scrum-board.html", context)

def extraCookieAcceptanceBanner(request):
	return render(request, "pages/extra-cookie-acceptance-banner.html")

def extraOrders(request):
	return render(request, "pages/extra-orders.html")

def extraOrderDetails(request):
	return render(request, "pages/extra-order-details.html")

def extraProducts(request):
	return render(request, "pages/extra-products.html")

def extraProductDetails(request):
	return render(request, "pages/extra-product-details.html")

def extraFileManager(request):
	context = {
		"appSidebarMinified": 1,
		"appHeaderInverse": 1,
		"appContentFullHeight": 1,
		"appContentClass": "d-flex flex-column"
	}
	return render(request, "pages/extra-file-manager.html", context)

def extraPricing(request):
	return render(request, "pages/extra-pricing.html")

def extraMessenger(request):
	context = {
		"appSidebarMinified": 1,
		"appHeaderInverse": 1,
		"appContentClass": "p-0",
		"appContentFullHeight": 1
	}
	return render(request, "pages/extra-messenger.html", context)

def extraDataManagement(request):
	context = {
		"appSidebarMinified": 1,
		"appHeaderInverse": 1,
		"appContentClass": "p-0 bg-component",
		"appContentFullHeight": 1
	}
	return render(request, "pages/extra-data-management.html", context)

def extraSettings(request):
	return render(request, "pages/extra-settings.html")
	
def userLoginV1(request):
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/user-login-v1.html", context)

def userLoginV2(request):
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/user-login-v2.html", context)

def userLoginV3(request):
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": "p-0"
	}
	return render(request, "pages/user-login-v3.html", context)

def userRegisterV3(request):
	register_comuns = sorted(
		common_catalog(),
		key=lambda item: (str(item.get('cidade') or ''), str(item.get('comum') or '')),
	)
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": "p-0",
		"register_comuns": register_comuns,
	}
	return render(request, "pages/user-register-v3.html", context)

def logout_view(request):
    profile = update_profile_activity(request.session.get('user_profile') or {}, 'logout')
    request.session['user_profile'] = profile
    close_access_session(request)
    log_audit(request, 'LOGOUT', 'AUTH', {
        "email": profile.get('email'), "role_id": profile.get('role_id'),
        "comum": profile.get('comum')
    })
    request.session.flush()
    return redirect('/user/login-v1')

def helperCss(request):
	return render(request, "pages/helper-css.html")
	
def error404(request):
	context = {
		"appSidebarHide": 1,
		"appHeaderHide": 1,
		"appContentClass": 'p-0'
	}
	return render(request, "pages/extra-error.html", context)

def handler404(request, exception = None):
	# Preserve o status 404 para que o CommonMiddleware possa aplicar
	# APPEND_SLASH quando existir uma rota equivalente com barra final.
	response = error404(request)
	response.status_code = 404
	return response
