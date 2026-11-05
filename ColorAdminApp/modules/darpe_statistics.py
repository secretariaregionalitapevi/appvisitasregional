"""Publicações periódicas: nenhuma atualização apaga a competência anterior."""
import json
import logging
import re
from datetime import date

import requests
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .access_control import service_headers
from .darpe_library import allowed, can_publish

logger = logging.getLogger(__name__)
METRICS = {
    'unidades': 'Unidades constituídas', 'batismos': 'Batismos desde 2010',
    'pessoas_batizadas': 'Pessoas batizadas', 'colaboradores': 'Ministério e colaboradores',
    'atendimentos': 'Unidades com atendimentos formalizados',
}


def validate(payload):
    reference = str(payload.get('competencia', ''))
    if not re.fullmatch(r'\d{4}-\d{2}', reference):
        raise ValueError('Informe a competência no formato ano-mês.')
    try:
        first = date.fromisoformat(reference + '-01')
    except ValueError as exc:
        raise ValueError('Competência inválida.') from exc
    if first > timezone.localdate():
        raise ValueError('A competência não pode estar no futuro.')
    result = {'competencia': first.isoformat()}
    for key in METRICS:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2147483647:
            raise ValueError('Preencha todos os indicadores com números inteiros não negativos.')
        result[key] = value
    for key, limit in [('fonte', 500), ('observacoes', 3000), ('distribuicao', 3000)]:
        result[key] = str(payload.get(key) or '').strip()
        if len(result[key]) > limit:
            raise ValueError(f'{key.capitalize()}: limite de {limit} caracteres.')
    if not result['fonte']:
        raise ValueError('Informe a fonte dos dados.')
    return result


def timeline(rows):
    """Uma versão vigente por competência, conservando todas as revisões."""
    latest = {}
    for row in sorted(rows, key=lambda r: (r['competencia'], r['created_at'], str(r['id']))):
        latest[row['competencia']] = row
    return [latest[key] for key in sorted(latest)]


@never_cache
@require_http_methods(['GET', 'POST'])
def api(request):
    if not allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    url = settings.SUPABASE_URL + '/rest/v1/darpe_estatisticas'
    try:
        if request.method == 'POST':
            if not can_publish(request):
                return JsonResponse({'error': 'Somente a gestão regional pode publicar estatísticas.'}, status=403)
            try:
                payload = json.loads(request.body)
                if not isinstance(payload, dict):
                    raise ValueError('Envie os dados da publicação.')
                data = validate(payload)
            except (ValueError, TypeError) as exc:
                return JsonResponse({'error': str(exc)}, status=400)
            profile = request.session.get('user_profile') or {}
            data['created_by'] = str(request.session.get('user_id') or '')
            data['responsavel'] = str(profile.get('full_name') or profile.get('nome') or 'Gestão DARPE')[:160]
            response = requests.post(url, headers={**service_headers(), 'Prefer': 'return=representation'}, json=data, timeout=20)
            response.raise_for_status()
            return JsonResponse({'message': 'Publicação registrada. O histórico anterior foi preservado.'}, status=201)
        rows = []
        while True:
            response = requests.get(url, headers=service_headers(), params={'select': 'id,competencia,unidades,batismos,pessoas_batizadas,colaboradores,atendimentos,fonte,observacoes,distribuicao,responsavel,created_at', 'order': 'competencia.asc,created_at.asc,id.asc', 'limit': 500, 'offset': len(rows)}, timeout=20)
            response.raise_for_status()
            batch = response.json()
            rows.extend(batch)
            if len(batch) < 500:
                break
        return JsonResponse({'items': timeline(rows), 'versions': rows, 'metrics': METRICS, 'can_publish': can_publish(request)})
    except requests.RequestException:
        logger.exception('Falha no histórico de estatísticas DARPE')
        return JsonResponse({'error': 'Não foi possível acessar as estatísticas. Tente novamente.'}, status=503)
