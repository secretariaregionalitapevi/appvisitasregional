"""Ações reais do File Manager; objetos anteriores nunca são sobrescritos."""
import json
import logging
from uuid import UUID, uuid4
import requests
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .access_control import service_headers, user_scope
from . import darpe_library as library

logger = logging.getLogger(__name__)
ROOTS = dict(zip(('documentos', 'instrumentos', 'setores'), ('00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000003')))


def url(table):
    return settings.SUPABASE_URL + '/rest/v1/' + table


def read(table, params):
    response = requests.get(url(table), headers=service_headers(), params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def record(record_id):
    rows = read('darpe_documentos', {'id': 'eq.' + str(record_id), 'select': '*', 'limit': 1})
    return rows[0] if rows else None


def folder(folder_id):
    try:
        folder_id = str(UUID(str(folder_id)))
    except ValueError as exc:
        raise ValueError('Selecione uma pasta válida.') from exc
    rows = read('darpe_pastas', {'id': 'eq.' + folder_id, 'select': '*', 'limit': 1})
    if not rows:
        raise ValueError('Pasta não encontrada. Atualize a lista.')
    return rows[0]


def metadata(data):
    title = str(data.get('titulo') or '').strip()
    description = str(data.get('descricao') or '').strip()
    name = str(data.get('original_name') or '').strip()
    if not title or len(title) > 160 or len(description) > 2000:
        raise ValueError('Informe título de até 160 caracteres e descrição de até 2.000 caracteres.')
    if not name.lower().endswith('.pdf') or len(name) > 255 or any(c in name for c in '/\\\r\n\x00'):
        raise ValueError('Informe um nome de arquivo PDF, sem caminhos ou quebras de linha.')
    return {'titulo': title, 'descricao': description, 'original_name': name}


@never_cache
@require_http_methods(['GET', 'POST'])
def folders(request):
    if not library.allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    try:
        if request.method == 'GET':
            items = []
            while True:
                batch = read('darpe_pastas', {'select': 'id,nome,parent_id,categoria,sistema,created_at', 'order': 'nome.asc,id.asc', 'limit': 500, 'offset': len(items)})
                items.extend(batch)
                if len(batch) < 500:
                    break
            return JsonResponse({'items': items})
        if not library.can_publish(request):
            return JsonResponse({'error': 'Somente a gestão regional pode organizar pastas.'}, status=403)
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('Informe os dados da pasta.')
        name = str(data.get('nome') or '').strip()
        if not name or len(name) > 100 or any(c in name for c in '/\\\r\n\x00'):
            raise ValueError('Informe nome de pasta de até 100 caracteres, sem barras.')
        if data.get('id'):
            current = folder(data['id'])
            if current['sistema']:
                return JsonResponse({'error': 'As três pastas principais são fixas.'}, status=403)
            response = requests.patch(url('darpe_pastas'), headers=service_headers(), params={'id': 'eq.' + current['id']}, json={'nome': name}, timeout=20)
            if response.status_code == 409:
                return JsonResponse({'error': 'Já existe uma pasta com esse nome neste local.'}, status=409)
            response.raise_for_status()
            return JsonResponse({'message': 'Pasta renomeada.'})
        parent = folder(data.get('parent_id'))
        payload = {'nome': name, 'parent_id': parent['id'], 'categoria': parent['categoria'], 'created_by': str(request.session.get('user_id') or '')}
        response = requests.post(url('darpe_pastas'), headers=service_headers(), json=payload, timeout=20)
        if response.status_code == 409:
            return JsonResponse({'error': 'Já existe uma pasta com esse nome neste local.'}, status=409)
        if response.status_code == 400:
            raise ValueError('Não foi possível criar a pasta nessa hierarquia.')
        response.raise_for_status()
        return JsonResponse({'message': 'Pasta criada.'}, status=201)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        logger.exception('Falha nas pastas DARPE')
        return JsonResponse({'error': 'Não foi possível acessar as pastas. Tente novamente.'}, status=503)


@never_cache
@require_http_methods(['GET'])
def versions(request, record_id):
    if not library.allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    try:
        current = record(record_id)
        if not current or (current.get('deleted_at') and user_scope(request)['level'] not in {'global', 'regional'}):
            return JsonResponse({'error': 'Documento não encontrado.'}, status=404)
        items = []
        while True:
            batch = read('darpe_documento_versoes', {'documento_id': 'eq.' + str(record_id), 'select': 'id,version,snapshot,created_at', 'order': 'version.desc', 'limit': 500, 'offset': len(items)})
            items.extend(batch)
            if len(batch) < 500:
                break
        # Não enviar caminhos internos nem identificadores dos operadores ao navegador.
        visible = []
        for row in items:
            snap = row['snapshot']
            visible.append({'id': row['id'], 'version': row['version'], 'created_at': row['created_at'], **{key: snap.get(key) for key in ('titulo', 'descricao', 'original_name', 'byte_size', 'pasta_id', 'deleted_at')}})
        return JsonResponse({'items': visible})
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível consultar as versões.'}, status=503)


@never_cache
@require_http_methods(['POST'])
def update(request, record_id):
    if not library.can_publish(request):
        return JsonResponse({'error': 'Somente a gestão regional pode editar documentos.'}, status=403)
    new_object_url = None
    try:
        current = record(record_id)
        if not current:
            return JsonResponse({'error': 'Documento não encontrado.'}, status=404)
        try:
            expected = int(request.POST.get('version', ''))
        except ValueError as exc:
            raise ValueError('Atualize a lista antes de editar o documento.') from exc
        if expected != current['version']:
            return JsonResponse({'error': 'Este arquivo foi alterado por outro usuário. Atualize a lista.'}, status=409)
        action = request.POST.get('action', 'edit')
        if action == 'archive':
            changes = {'deleted_at': timezone.now().isoformat()}
        elif action == 'restore':
            changes = {'deleted_at': None}
        elif action == 'move':
            if current.get('deleted_at'):
                raise ValueError('Restaure o arquivo antes de movê-lo.')
            changes = {'pasta_id': folder(request.POST.get('pasta_id'))['id']}
        elif action == 'restore_version':
            revisions = read('darpe_documento_versoes', {'id': 'eq.' + str(UUID(request.POST.get('revision_id', ''))), 'documento_id': 'eq.' + str(record_id), 'select': 'snapshot', 'limit': 1})
            if not revisions:
                raise ValueError('Versão não encontrada.')
            snap = revisions[0]['snapshot']
            changes = {key: snap[key] for key in ('titulo', 'descricao', 'original_name', 'byte_size', 'object_path', 'pasta_id')}
            changes['deleted_at'] = None
        elif action == 'edit':
            if current.get('deleted_at'):
                raise ValueError('Restaure o arquivo antes de editá-lo.')
            changes = metadata(request.POST)
            changes['pasta_id'] = folder(request.POST.get('pasta_id'))['id']
            upload = request.FILES.get('arquivo')
            if upload:
                data = library.validate_pdf(upload)
                object_path = str(uuid4()) + '.pdf'
                new_object_url = settings.SUPABASE_URL + '/storage/v1/object/' + library.BUCKET + '/' + object_path
                response = requests.post(new_object_url, headers={**service_headers(), 'Content-Type': 'application/pdf'}, data=data, timeout=60)
                response.raise_for_status()
                changes.update(object_path=object_path, byte_size=len(data))
        else:
            raise ValueError('Ação inválida.')
        changes['updated_by'] = str(request.session.get('user_id') or '')
        response = requests.patch(url('darpe_documentos'), headers={**service_headers(), 'Prefer': 'return=representation'}, params={'id': 'eq.' + str(record_id), 'version': 'eq.' + str(expected)}, json=changes, timeout=20)
        response.raise_for_status()
        updated = response.json()
        if not updated:
            if new_object_url:
                requests.delete(new_object_url, headers=service_headers(), timeout=20)
            return JsonResponse({'error': 'O arquivo mudou durante a edição. Atualize a lista e tente novamente.'}, status=409)
        new_object_url = None
        return JsonResponse({'message': 'Documento atualizado. A versão anterior foi preservada.'})
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        # Não excluir após timeout: a escrita pode ter sido concluída pelo banco.
        logger.exception('Falha ao atualizar documento DARPE')
        return JsonResponse({'error': 'Não foi possível confirmar a atualização. Atualize a lista antes de tentar novamente.'}, status=503)
