"""Personal account pages; access permissions are never self-editable."""
import base64
import binascii
import io
import logging
import re
import warnings
from uuid import UUID

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.core.cache import cache

logger = logging.getLogger(__name__)


@never_cache
@require_http_methods(['GET'])
def postcode(request):
    if not request.session.get('authenticated') or not request.session.get('user_id'):
        return JsonResponse({'error': 'Sua sessão expirou. Entre novamente.'}, status=401)
    digits = re.sub(r'\D', '', request.GET.get('cep', ''))
    if len(digits) != 8:
        return JsonResponse({'error': 'Informe um CEP com 8 dígitos.'}, status=400)
    address = cache.get('account-cep:' + digits)
    if address is not None:
        return JsonResponse(address)
    try:
        response = requests.get(f'https://viacep.com.br/ws/{digits}/json/', timeout=(3.05, 5))
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError('Invalid postcode response')
        if result.get('erro'):
            return JsonResponse({'error': 'CEP não encontrado. Confira os números.'}, status=404)
        address = {key: result.get(key, '') for key in ('cep', 'logradouro', 'bairro', 'localidade', 'uf')}
        if not all(isinstance(value, str) for value in address.values()):
            raise ValueError('Invalid address fields')
        cache.set('account-cep:' + digits, address, 86400)
        return JsonResponse(address)
    except (requests.RequestException, ValueError):
        return JsonResponse({'error': 'Não foi possível consultar o CEP. Tente novamente ou preencha o endereço manualmente.'}, status=503)

PERSONAL_FIELDS = {'telefone': 30, 'celular': 30, 'whatsapp': 30, 'cep': 9,
                   'logradouro_numero': 250, 'bairro': 120, 'complemento': 180}


def account_context(request):
    account = request.session.get('user_profile') or {}
    address = account.get('logradouro_numero') or account.get('endereco') or ''
    parts = re.fullmatch(r'(.+),\s*(\d+[\w /-]*|s/n)', address, re.IGNORECASE)
    try:
        level = {1: 'Global', 2: 'Regional', 3: 'Municipal', 4: 'Local'}.get(int(account.get('role_id') or 0), 'Não informado')
    except (TypeError, ValueError):
        level = 'Não informado'
    return {'account': account, 'account_level': level,
            'account_street': parts[1] if parts else address,
            'account_number': parts[2] if parts else '',
            'account_initials': ''.join(part[0] for part in str(account.get('full_name') or 'Usuário').split()[:2]).upper()}


def avatar_content(upload):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if upload.size > 5 * 1024 * 1024:
        raise ValueError('Escolha uma foto de até 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > 20_000_000:
                    raise ValueError('Use uma imagem JPG, PNG ou WebP de até 20 megapixels.')
                photo = ImageOps.fit(ImageOps.exif_transpose(image).convert('RGB'), (256, 256))
                buffer = io.BytesIO()
                photo.save(buffer, format='JPEG', quality=82, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('A foto não é uma imagem válida. Use JPG, PNG ou WebP.') from None
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


@never_cache
@require_http_methods(['GET', 'POST'])
def profile(request):
    if not request.session.get('authenticated') or not request.session.get('user_id'):
        return redirect('/user/login-v1')
    current = request.session.get('user_profile') or {}
    if request.method == 'GET':
        return render(request, 'pages/extra-profile.html', account_context(request))
    name = ' '.join(request.POST.get('full_name', '').split())
    if not 2 <= len(name) <= 180 or any(ord(c) < 32 for c in name):
        return JsonResponse({'error': 'Informe seu nome com 2 a 180 caracteres.'}, status=400)
    changes = {'full_name': name}
    try:
        if 'logradouro' in request.POST or 'numero' in request.POST:
            street = ' '.join(request.POST.get('logradouro', '').split())
            number = ' '.join(request.POST.get('numero', '').split())
            if len(street) > 220 or len(number) > 25 or (number and not street):
                raise ValueError('Confira o logradouro e o número do endereço.')
            changes['logradouro_numero'] = ', '.join(filter(None, (street, number)))
        for key, limit in PERSONAL_FIELDS.items():
            if key == 'logradouro_numero' and key in changes:
                continue
            if key not in request.POST:
                continue
            value = ' '.join(request.POST[key].split())
            if len(value) > limit:
                raise ValueError('Confira o tamanho dos campos de contato e endereço.')
            digits = re.sub(r'\D', '', value)
            if key in {'telefone', 'celular', 'whatsapp'} and value and not 10 <= len(digits) <= 13:
                raise ValueError('Informe os telefones com DDD ou deixe o campo vazio.')
            if key == 'cep' and value and len(digits) != 8:
                raise ValueError('Informe um CEP com 8 dígitos ou deixe o campo vazio.')
            if key == 'cep' and value:
                value = digits[:5] + '-' + digits[5:]
            changes[key] = value
        if request.FILES.get('avatar'):
            changes['avatar_url'] = avatar_content(request.FILES['avatar'])
        elif request.POST.get('remove_avatar') == '1':
            changes['avatar_url'] = None
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    try:
        user_id = str(UUID(str(request.session['user_id'])))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Sua sessão expirou. Entre novamente.'}, status=401)
    try:
        response = requests.patch(
            f'{settings.SUPABASE_URL}/rest/v1/profiles',
            headers={'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
                     'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
                     'Content-Type': 'application/json', 'Prefer': 'return=representation'},
            params={'user_id': f'eq.{user_id}', 'status': 'eq.approved', 'select': 'user_id,' + ','.join(changes)},
            json=changes, timeout=(3.05, 15),
        )
        response.raise_for_status()
        rows = response.json()
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or str(rows[0].get('user_id')) != user_id
                or any(rows[0].get(key) != value for key, value in changes.items())):
            raise ValueError('Profile update not confirmed')
    except (requests.RequestException, ValueError):
        logger.warning('Could not save personal account name')
        return JsonResponse({'error': 'Não foi possível salvar seu perfil. Tente novamente.'}, status=503)
    session_changes = dict(changes)
    if 'avatar_url' in changes and changes['avatar_url']:
        # Keep image bytes out of the encrypted cookie session.
        session_changes['avatar_url'] = reverse('ColorAdminApp:accountAvatar') + '?v=' + timezone.now().strftime('%Y%m%d%H%M%S%f')
    request.session['user_profile'] = {**current, **session_changes}
    from ColorAdminApp.views import log_audit
    log_audit(request, 'UPDATE_OWN_PROFILE', 'AUTH', {'fields': list(changes), 'full_name': name})
    return JsonResponse({'saved': True, 'full_name': name,
                         'avatar_url': request.session['user_profile'].get('avatar_url')})


@never_cache
@require_http_methods(['GET'])
def account_settings(request):
    if not request.session.get('authenticated') or not request.session.get('user_id'):
        return redirect('/user/login-v1')
    return render(request, 'pages/extra-settings.html', account_context(request))


@never_cache
@require_http_methods(['GET'])
def avatar(request):
    if not request.session.get('authenticated') or not request.session.get('user_id'):
        return HttpResponse(status=401)
    try:
        user_id = str(UUID(str(request.session['user_id'])))
        response = requests.get(f'{settings.SUPABASE_URL}/rest/v1/profiles',
            headers={'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
                     'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}'},
            params={'user_id': 'eq.' + user_id, 'status': 'eq.approved', 'select': 'avatar_url', 'limit': 1}, timeout=(3.05, 10))
        response.raise_for_status()
        rows = response.json()
        value = rows[0].get('avatar_url') or '' if rows else ''
        match = re.fullmatch(r'data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)', value)
        if not match:
            return HttpResponse(status=404)
        payload = base64.b64decode(re.sub(r'\s', '', match[2]), validate=True)
        if len(payload) > 5 * 1024 * 1024:
            return HttpResponse(status=404)
        result = HttpResponse(payload, content_type=match[1])
        result['X-Content-Type-Options'] = 'nosniff'
        return result
    except (requests.RequestException, ValueError, TypeError, KeyError, binascii.Error):
        return HttpResponse(status=503)
