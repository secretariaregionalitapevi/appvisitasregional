"""Biblioteca regional de PDFs e orientações do DARPE."""
import io
import logging
from uuid import uuid4
from urllib.parse import quote

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .access_control import service_headers, user_scope, scope_details
from .module_access import MODULE_DARPE, can_access_module

logger = logging.getLogger(__name__)
BUCKET = 'darpe-documentos'
MAX_BYTES = 20 * 1024 * 1024
SECTORS = [
    (1, 'Sistemas de Ressocialização e Socioeducativos', 'Atendimento em unidades prisionais masculinas e femininas e em unidades socioeducativas.'),
    (2, 'Clínicas de Dependentes e Albergues', 'Atendimento em clínicas de dependentes e albergues.'),
    (3, 'Forças de Segurança', 'Atendimento às forças de segurança.'),
    (4, 'Hospitais, Instituições para Idosos e Setor Educacional', 'Atendimento em hospitais, instituições para idosos, projetos educacionais e universidades. Incorpora o antigo setor 5.'),
]
WINDS = ['Flauta transversal', 'Oboé', "Oboé d’amore", 'Corne inglês', 'Fagote', 'Clarinete', 'Clarinete alto', 'Clarinete baixo', 'Saxofone soprano', 'Saxofone alto', 'Saxofone tenor', 'Saxofone barítono', 'Trompete', 'Cornet', 'Flugelhorn', 'Trompa', 'Trombone', 'Trombonito', 'Barítono', 'Eufônio', 'Tuba']


def instruments():
    rows = [{'name': 'Órgão / teclado (irmãs)', 's1': 'Unidades femininas', 's2': 'Com famílias', 's3': 'Permitido', 's4': 'Não indicado na tabela original', 'note': 'Condições específicas nos setores 1 e 2.'}]
    for name in ['Violino', 'Viola', 'Violoncelo']:
        rows.append({'name': name, 's1': 'Não permitido', 's2': 'Permitido', 's3': 'Permitido', 's4': 'Hospitais / idosos: permitido', 'note': 'Setor 1: restrição às cordas fora do instrumento.'})
    for name in WINDS:
        large = name in {'Tuba', 'Saxofone barítono'}
        rows.append({'name': name, 's1': 'Não permitido' if large else 'Permitido', 's2': 'Permitido', 's3': 'Permitido', 's4': 'Hospitais / idosos: somente ao ar livre', 'note': 'Setor 1: instrumento de grande porte.' if large else 'Hospitais / idosos: restrição por risco biológico.'})
    for index, row in enumerate(rows):
        family = ('Teclado', 'keyboard') if index == 0 else ('Cordas', 'strings') if index <= 3 else ('Madeiras', 'woodwinds') if index <= 15 else ('Metais', 'brass')
        row['family'], row['family_key'] = family
        row['cells'] = []
        for key in ('s1', 's2', 's3', 's4'):
            text = row[key]
            status = 'permitted' if text == 'Permitido' else 'restricted' if text == 'Não permitido' else 'conditional'
            if key == 's4':
                text = 'Hospitais / idosos' if index in (1, 2, 3) else 'Ao ar livre' if index > 3 else 'Sem indicação'
                status = 'conditional'
            row['cells'].append({'text': text, 'status': status, 'icon': {'permitted': 'fa-check', 'restricted': 'fa-minus', 'conditional': 'fa-circle-info'}[status]})
    return rows


def allowed(request):
    return bool(request.session.get('user_id') or request.session.get('authenticated')) and can_access_module(request, MODULE_DARPE)


def can_publish(request):
    return allowed(request) and user_scope(request)['level'] in {'global', 'regional'}


def endpoint():
    return settings.SUPABASE_URL + '/rest/v1/darpe_documentos'



def _pdf_object(value):
    return value.get_object() if hasattr(value, 'get_object') else value


def _is_content_credentials(spec):
    """C2PA é metadado de procedência; não autoriza anexos de outros tipos."""
    spec = _pdf_object(spec)
    if not isinstance(spec, dict) or spec.get('/AFRelationship') != '/C2PA_Manifest':
        return False
    if str(spec.get('/F') or spec.get('/UF') or '') != 'Content Credentials':
        return False
    streams = _pdf_object(spec.get('/EF'))
    if not isinstance(streams, dict) or not streams:
        return False
    return all(str(_pdf_object(stream).get('/Subtype', '')).lower().lstrip('/') == 'application/c2pa'
               for stream in streams.values())


def _only_content_credentials(tree):
    pending = [tree]
    seen = set()
    while pending:
        node = _pdf_object(pending.pop())
        if not isinstance(node, dict) or id(node) in seen or len(seen) >= 1000:
            return False
        seen.add(id(node))
        names = _pdf_object(node.get('/Names', []))
        if len(names) % 2 or any(not _is_content_credentials(names[i]) for i in range(1, len(names), 2)):
            return False
        pending.extend(_pdf_object(node.get('/Kids', [])))
    return True


def validate_pdf(upload):
    # O parser pertence ao fluxo de upload, não à inicialização de todas as rotas.
    from pypdf import PdfReader

    if not upload or not upload.name.lower().endswith('.pdf'):
        raise ValueError('Selecione um arquivo PDF.')
    if upload.size > MAX_BYTES:
        raise ValueError('O PDF deve ter no máximo 20 MB.')
    data = upload.read(MAX_BYTES + 1)
    if not data.startswith(b'%PDF-') or len(data) > MAX_BYTES:
        raise ValueError('Arquivo PDF inválido ou maior que 20 MB.')
    try:
        pdf = PdfReader(io.BytesIO(data))
        if pdf.is_encrypted or not len(pdf.pages):
            raise ValueError()
        # Não publicar PDFs com ações executáveis ou arquivos embutidos.
        root = pdf.trailer['/Root']
        names = _pdf_object(root.get('/Names', {}))
        if any(key in root for key in ('/OpenAction', '/AA')) or '/JavaScript' in names:
            raise ValueError()
        if '/EmbeddedFiles' in names and not _only_content_credentials(names['/EmbeddedFiles']):
            raise ValueError()
        associated = _pdf_object(root.get('/AF', []))
        if any(not _is_content_credentials(spec) for spec in associated):
            raise ValueError()
    except Exception as exc:
        raise ValueError('Use um PDF válido, sem senha, ações automáticas ou arquivos anexos.') from exc
    return data


@never_cache
def page(request, section='documentos'):
    if not allowed(request):
        return render(request, 'pages/403.html', status=403)
    return render(request, 'pages/darpe_library.html', {
        'section': section, 'can_publish': can_publish(request),
        'scope': scope_details(user_scope(request)), 'sectors': SECTORS,
        'instruments': instruments(),
    })


@never_cache
@require_http_methods(['GET', 'POST'])
def documents(request):
    if not allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    try:
        if request.method == 'GET':
            items = []
            manager = user_scope(request)['level'] in {'global', 'regional'}
            while True:
                params = {'select': 'id,titulo,descricao,categoria,original_name,byte_size,created_at,pasta_id,version,updated_at,deleted_at', 'order': 'updated_at.desc,id.asc', 'limit': 500, 'offset': len(items)}
                if not manager:
                    params['deleted_at'] = 'is.null'
                response = requests.get(endpoint(), headers=service_headers(), params=params, timeout=20)
                response.raise_for_status()
                batch = response.json()
                items.extend(batch)
                if len(batch) < 500:
                    break
            return JsonResponse({'items': items, 'can_manage': manager})
        if not can_publish(request):
            return JsonResponse({'error': 'Somente a gestão regional pode publicar documentos.'}, status=403)
        title = request.POST.get('titulo', '').strip()
        description = request.POST.get('descricao', '').strip()
        category = request.POST.get('categoria', 'documentos')
        if not title or len(title) > 160 or len(description) > 2000 or category not in {'documentos', 'instrumentos', 'setores'}:
            raise ValueError('Informe título de até 160 caracteres e uma categoria válida. Descrição: até 2.000 caracteres.')
        upload = request.FILES.get('arquivo')
        data = validate_pdf(upload)
        from .darpe_file_manager import ROOTS, folder
        target_folder = folder(request.POST.get('pasta_id') or ROOTS[category])
        record_id = str(uuid4())
        object_path = record_id + '.pdf'
        storage_url = settings.SUPABASE_URL + '/storage/v1/object/' + BUCKET + '/' + object_path
        stored = requests.post(storage_url, headers={**service_headers(), 'Content-Type': 'application/pdf'}, data=data, timeout=60)
        stored.raise_for_status()
        response = requests.post(endpoint(), headers=service_headers(), json={
            'id': record_id, 'titulo': title, 'descricao': description, 'categoria': category,
            'pasta_id': target_folder['id'],
            'object_path': object_path, 'original_name': upload.name[:255], 'byte_size': len(data),
            'created_by': str(request.session.get('user_id') or ''),
        }, timeout=20)
        if not response.ok:
            requests.delete(storage_url, headers=service_headers(), timeout=20)
        response.raise_for_status()
        return JsonResponse({'message': 'PDF publicado e disponível para download.'}, status=201)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        logger.exception('Falha na biblioteca DARPE')
        return JsonResponse({'error': 'Não foi possível acessar a biblioteca. Tente novamente.'}, status=503)


@never_cache
@require_http_methods(['GET'])
@xframe_options_sameorigin
def download(request, record_id, inline=False):
    if not allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    try:
        response = requests.get(endpoint(), headers=service_headers(), params={'id': 'eq.' + str(record_id), 'select': 'object_path,original_name,deleted_at', 'limit': 1}, timeout=20)
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return JsonResponse({'error': 'Documento não encontrado.'}, status=404)
        row = rows[0]
        if row.get('deleted_at') and user_scope(request)['level'] not in {'global', 'regional'}:
            return JsonResponse({'error': 'Documento não encontrado.'}, status=404)
        if request.GET.get('revision'):
            from uuid import UUID
            try:
                revision_id = str(UUID(request.GET['revision']))
            except ValueError:
                return JsonResponse({'error': 'Versão inválida.'}, status=400)
            versions = requests.get(settings.SUPABASE_URL + '/rest/v1/darpe_documento_versoes', headers=service_headers(), params={'id': 'eq.' + revision_id, 'documento_id': 'eq.' + str(record_id), 'select': 'snapshot', 'limit': 1}, timeout=20)
            versions.raise_for_status()
            if not versions.json():
                return JsonResponse({'error': 'Versão não encontrada.'}, status=404)
            row = versions.json()[0]['snapshot']
        response = requests.get(settings.SUPABASE_URL + '/storage/v1/object/authenticated/' + BUCKET + '/' + quote(row['object_path'], safe=''), headers=service_headers(), timeout=60)
        response.raise_for_status()
        result = HttpResponse(response.content, content_type='application/pdf')
        result['Content-Disposition'] = ('inline' if inline else 'attachment') + "; filename*=UTF-8''" + quote(row['original_name'], safe='')
        result['X-Content-Type-Options'] = 'nosniff'
        return result
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível baixar o PDF. Tente novamente.'}, status=503)
