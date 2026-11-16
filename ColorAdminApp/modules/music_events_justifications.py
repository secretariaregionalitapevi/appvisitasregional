"""Importação conferida de justificativas; documentos são dados, nunca instruções."""
import csv
import io
import json
import re
import unicodedata
import hashlib
from pathlib import Path
from uuid import uuid4
from copy import copy
from zipfile import BadZipFile

import requests
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from pypdf.errors import PdfReadError
from PIL import UnidentifiedImageError

from . import music_events as events
from .access_control import common_catalog, user_scope
from .music_events_identity import CommonResolver, normalized_name
from .music_events_import import is_conductor_role, norm, person_names
from .music_conductor_identity import conductor_name


def metadata(notes):
    try:
        value = json.loads(notes or '')
        return value if isinstance(value, dict) and value.get('_justificativa') == 1 else {}
    except (ValueError, TypeError):
        return {}


def pack_metadata(value):
    return json.dumps({'_justificativa': 1, **value}, ensure_ascii=False)


def display_note(notes):
    value = metadata(notes)
    return value.get('motivo', '') if value else notes


def reason_summary(notes):
    """Texto da coluna Motivo, sem repetir os nomes da coluna anterior."""
    value = metadata(notes)
    people = value.get('pessoas')
    if isinstance(people, list):
        reasons = {}
        for person in people:
            if not isinstance(person, dict) or person.get('excluida'):
                continue
            reason = str(person.get('motivo') or '').strip()
            if reason:
                reasons.setdefault(norm(reason), reason)
        if reasons:
            return ' | '.join(reasons.values())
    return display_note(notes)


def registered_name_matches(source, registered, common_key=''):
    # Somente a divergência ortográfica confirmada usa alias na importação.
    # Nomes abreviados continuam exigindo correspondência única no cadastro.
    if common_key == 'BR-22-1804':
        source = conductor_name(source, common_key)
        registered = conductor_name(registered, common_key)
    source_tokens = set(normalized_name(source).split())
    if not source_tokens:
        return set()
    names = person_names(registered) or [str(registered or '')]
    if common_key == 'BR-22-1804':
        names = [conductor_name(name, common_key) for name in names]
    return {normalized_name(name) for name in names
            if source_tokens == set(normalized_name(name).split()) or
            len(source_tokens) > 1 and source_tokens <= set(normalized_name(name).split())}


def block_key(row):
    label = str(row.get('bloco_origem') or row.get('nome_evento') or row.get('ensaio_id') or 'Bloco único')
    identity = '|'.join([str(row.get('data_evento') or ''), str(row.get('tipo_evento') or ''), str(row.get('ensaio_id') or ''), label])
    return hashlib.sha256(identity.encode()).hexdigest()[:24], label


def blocks(rows):
    result = {}
    for row in rows:
        key, label = block_key(row)
        item = result.setdefault(key, {'id': key, 'nome': label, 'data': str(row.get('data_evento') or ''), 'total': 0})
        item['total'] += 1
    return list(result.values())


def table_rows(rows):
    aliases = {'nome': ('NOME', 'NOME COMPLETO'), 'comum': ('COMUM', 'COMUM CONGREGACAO', 'COMUM DE CONGREGACAO'),
               'cargo': ('CARGO', 'CARGO OU MINISTERIO', 'CARGO MINISTERIO'),
               'municipio': ('MUNICIPIO', 'CIDADE'), 'motivo': ('MOTIVO', 'MOTIVO DA AUSENCIA', 'JUSTIFICATIVA'),
               'data_evento': ('DATA EVENTO', 'DATA DO EVENTO', 'DATA')}
    aliases.update(bloco_origem=('EVENTO', 'ENSAIO', 'NOME EVENTO', 'NOME DO EVENTO', 'BLOCO'), ensaio_id=('ENSAIO ID',))
    header = None
    output = []
    for row in rows:
        if header is None:
            header = {field: i for i, value in enumerate(row) for field, names in aliases.items()
                      if norm(value).replace('_', ' ') in names}
            if not {'nome', 'comum', 'cargo', 'motivo'} <= header.keys():
                header = None
            continue
        output.append({key: str(row[i] or '').strip() if i < len(row) else '' for key, i in header.items()})
    return output


def text_rows(text):
    lines = text.splitlines()
    # PDFs do formulário: os limites vêm do cabeçalho, inclusive nomes sem espaços entre colunas.
    output = []
    columns = None
    context = {}
    for line in lines:
        normalized = ''.join(c for c in unicodedata.normalize('NFD', line.upper()) if not unicodedata.combining(c))
        dates = re.findall(r'\b\d{2}/\d{2}/\d{4}\b', line)
        if dates and ('ENSAIO' in normalized or 'JUSTIFICATIVA' in normalized):
            context = {'data_evento': dates[-1], 'bloco_origem': line.strip()}
            columns = None
            continue
        if 'COMUM' in normalized and 'CARGO' in normalized and 'NOME' in normalized:
            columns = [normalized.index(x) for x in ('NOME', 'COMUM', 'CARGO', 'MOTIVO')]
            continue
        if not columns or not re.match(r'^\s*\d+\s+', line):
            continue
        a, b, c, d = columns
        role = re.search(r'Encarregado (?:Local|de orquestra|Regional)', line, re.I)
        if role:
            left = re.sub(r'^\s*\d+\s+', '', line[:role.start()]).strip()
            parts = re.split(r'\s{2,}', left)
            name, common = (parts[0], ' '.join(parts[1:])) if len(parts) > 1 else (line[a:b].strip(), line[b:role.start()].strip())
            output.append({'nome': name, 'comum': common, 'cargo': role.group(),
                           'motivo': re.split(r'\s{4,}', line[role.end():].strip())[0]})
        else:
            output.append({'nome': line[a:b].strip(), 'comum': line[b:c].strip(),
                           'cargo': line[c:d].strip(), 'motivo': re.split(r'\s{4,}', line[d:].strip())[0]})
        output[-1].update(context)
    if not output:
        # OCR normalmente preserva separações de colunas por múltiplos espaços.
        output = table_rows(re.split(r'\s{2,}|\t', item.strip()) for item in lines)
    return output


def read_upload(upload):
    if upload.size > 12 * 1024 * 1024:
        raise ValueError('Use um arquivo de até 12 MB.')
    suffix = Path(upload.name).suffix.lower()
    if suffix == '.xlsx':
        from openpyxl import load_workbook
        book = load_workbook(upload, read_only=True, data_only=True)
        try:
            result = []
            for sheet in book:
                if not sheet.max_row or not sheet.max_column:
                    sheet.calculate_dimension(force=True)
                if sheet.max_row * sheet.max_column > 200000:
                    raise ValueError('Planilha limitada a 200 mil células por aba.')
                result.extend(table_rows(sheet.iter_rows(values_only=True)))
            return result
        finally:
            book.close()
    if suffix == '.csv':
        text = upload.read().decode('utf-8-sig')
        return table_rows(csv.reader(io.StringIO(text), csv.Sniffer().sniff(text[:8192], delimiters=',;\t')))
    from .exam_import import ocr_image
    if suffix == '.pdf':
        from pypdf import PdfReader
        content = upload.read()
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > 30:
            raise ValueError('PDF limitado a 30 páginas.')
        texts = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text(extraction_mode='layout') or ''
            if not text.strip():
                import pypdfium2 as pdfium
                with pdfium.PdfDocument(content) as document:
                    buffer = io.BytesIO()
                    document[index].render(scale=2).to_pil().save(buffer, format='PNG')
                    text = ocr_image(buffer.getvalue())
            texts.append(text)
        result = text_rows('\n'.join(texts))
        return result
    if suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
        return text_rows(ocr_image(upload.read()))
    raise ValueError('Use PDF, Excel (.xlsx), CSV ou imagem PNG/JPG/WebP.')


def reconcile(rows, catalog, leaders, day):
    resolver = CommonResolver(catalog)
    active_leaders = [person for person in leaders
                      if is_conductor_role(person.get('cargo_ministerio'))
                      and norm(person.get('status')) not in {'INATIVO', 'EXCLUIR'}]
    output = []
    seen = set()
    for raw in rows:
        row = {key: str(value or '').strip() for key, value in raw.items()}
        if not is_conductor_role(row.get('cargo')):
            continue
        common = resolver.resolve(row.get('comum'), row.get('municipio'))
        if not common and not row.get('municipio'):
            matches = {c['comum']: c for c in catalog if resolver.resolve(row.get('comum'), c['cidade']) == c}
            common = next(iter(matches.values())) if len(matches) == 1 else None
            if not common:
                source_matches = {events.code(c['comum']): c for c in catalog
                                  if resolver.resolve(row.get('comum'), c['cidade']) == c}
                named_commons = {}
                for person in active_leaders:
                    if normalized_name(person.get('nome_aluno')) != normalized_name(row.get('nome')):
                        continue
                    registered_common = resolver.resolve(person.get('comum_congregacao'), person.get('municipio'))
                    if registered_common and events.code(registered_common['comum']) in source_matches:
                        key = events.code(registered_common['comum'])
                        named_commons[key] = source_matches[key]
                if len(named_commons) == 1:
                    common = next(iter(named_commons.values()))
        row.update(comum_chave=events.code(common['comum']) if common else '',
                   municipio=common['cidade'] if common else row.get('municipio', ''),
                   comum_identificada=common['comum'] if common else '', problema='')
        registered = [p for p in active_leaders if common
                      and resolver.resolve(p.get('comum_congregacao'), p.get('municipio')) == common]
        row['encarregado'] = ', '.join(p.get('nome_aluno', '') for p in registered)
        matched_names = []
        if not common:
            row['problema'] = 'Comum não identificada ou ambígua.'
        else:
            candidates_by_name = {
                normalized_name(conductor_name(name, row['comum_chave']) if row['comum_chave'] == 'BR-22-1804' else name): name
                for person in registered
                for name in person_names(person.get('nome_aluno'))
            }
            for source_name in person_names(row.get('nome')):
                matches = set().union(*(registered_name_matches(source_name, person.get('nome_aluno'), row['comum_chave'])
                                        for person in registered))
                if len(matches) != 1:
                    row['problema'] = 'Nome/cargo não confirmado no cadastro de encarregados locais.'
                    break
                matched_names.append(candidates_by_name[next(iter(matches))])
            if not matched_names:
                row['problema'] = 'Nome/cargo não confirmado no cadastro de encarregados locais.'
            elif not row['problema']:
                matched_names = list(dict.fromkeys(matched_names))
        source_date = row.get('data_evento', '')[:10]
        if source_date and source_date != day:
            from datetime import datetime
            try:
                source_date = datetime.strptime(source_date, '%d/%m/%Y').date().isoformat()
            except ValueError:
                pass
            if source_date != day:
                row['problema'] = 'Data da justificativa diferente do evento selecionado.'
        if not row['problema']:
            for name in matched_names:
                identity = (row['comum_chave'], normalized_name(name))
                individual = {**row, 'nome': name, 'encarregado': name,
                              'encarregados_identificados': [name], 'problema': ''}
                if identity in seen:
                    individual['problema'] = 'Encarregado repetido neste lote; a pessoa será registrada uma única vez.'
                else:
                    seen.add(identity)
                output.append(individual)
            continue
        output.append(row)
    return output


@require_POST
def api(request, event_id, action):
    if not events._allowed(request) or user_scope(request)['level'] not in {'regional', 'global'}:
        return JsonResponse({'error': 'Importação restrita à administração regional.'}, status=403)
    profile = request.session.get('user_profile') or {}
    actor = request.session.get('user_id') or profile.get('user_id')
    if not actor:
        return JsonResponse({'error': 'Entre novamente para identificar o responsável.'}, status=401)
    try:
        event = next((e for e in events._visible_events(request) if e['id'] == str(event_id)), None)
        if not event:
            return JsonResponse({'error': 'Evento não encontrado.'}, status=404)
        if action == 'listar':
            rows = events._read('musica_evento_encarregados', evento_id=f'eq.{event_id}', situacao='eq.JUSTIFICOU', order='created_at.desc,id.asc')
            items = []
            for row in rows:
                if row.get('evento_id') != str(event_id) or row.get('situacao') != 'JUSTIFICOU':
                    continue
                info = metadata(row.get('observacoes'))
                people = info.get('pessoas')
                if isinstance(people, list) and len(people) > 1:
                    for index, person in enumerate(people):
                        if person.get('excluida') or person.get('situacao', row['situacao']) != 'JUSTIFICOU':
                            continue
                        reason = person.get('motivo') or ''
                        items.append({**row, 'id': f"{row['id']}:{index}", 'nome': person['nome'],
                                      'motivo': reason, 'motivo_resumido': reason, 'observacoes': reason,
                                      'lote': info.get('lote', ''), 'origem': info.get('origem', 'Conferência manual / legado'),
                                      'bloco': info.get('bloco', '')})
                    continue
                items.append({**row, 'motivo': display_note(row.get('observacoes')),
                              'motivo_resumido': reason_summary(row.get('observacoes')),
                              'nome': row.get('encarregado_nome') or info.get('nome', ''),
                              'lote': info.get('lote', ''), 'origem': info.get('origem', 'Conferência manual / legado'),
                              'bloco': info.get('bloco', ''), 'observacoes': display_note(row.get('observacoes'))})
            return JsonResponse({'items': items, 'evento': event})
        if action == 'cadastro':
            catalog = common_catalog()
            resolver = CommonResolver(catalog)
            commons = {}
            for person in events._registry():
                if not is_local_conductor_role(person.get('cargo_ministerio')) or norm(person.get('status')) in {'INATIVO', 'EXCLUIR'}:
                    continue
                common = resolver.resolve(person.get('comum_congregacao'), person.get('municipio'))
                if not common:
                    continue
                key = events.code(common['comum'])
                item = commons.setdefault(key, {'id': key, 'comum': common['comum'], 'municipio': common['cidade'], 'encarregados': []})
                for name in person_names(person.get('nome_aluno')):
                    if name not in item['encarregados']:
                        item['encarregados'].append(name)
            return JsonResponse({'comuns': sorted(commons.values(), key=lambda row: (row['municipio'], row['comum']))})
        if event['status'] == 'ENCERRADO':
            return JsonResponse({'error': 'Reabra o evento antes de importar justificativas.'}, status=409)
        if action == 'registrar':
            raw = json.loads(request.body or '{}')
            reason = str(raw.get('motivo') or '').strip()
            if not reason or len(reason) > 500:
                raise ValueError('Informe um motivo de até 500 caracteres.')
            rows = reconcile([{'nome': raw.get('nome'), 'comum': raw.get('comum_chave'),
                               'cargo': 'Encarregado Local', 'motivo': reason}],
                             common_catalog(), events._registry(), event['data_evento'])
            if not rows or rows[0]['problema']:
                raise ValueError('Selecione a comum e um encarregado cadastrado nela.')
            row = rows[0]
            existing = [item for item in events._read(
                'musica_evento_encarregados', evento_id=f'eq.{event_id}',
                comum_chave='eq.' + row['comum_chave'])
                if normalized_name(item.get('encarregado_nome')
                                   or metadata(item.get('observacoes')).get('nome')) == normalized_name(row['nome'])]
            if any(not metadata(item.get('observacoes')).get('excluida') for item in existing):
                return JsonResponse({'error': 'Este encarregado já possui conferência neste evento. Utilize a edição do registro existente.'}, status=409)
            child = copy(request)
            child._body = json.dumps({'comum_chave': row['comum_chave'], 'encarregado_nome': row['nome'],
                                      'situacao': 'JUSTIFICOU', 'observacoes': reason}).encode('utf-8')
            child._justification_metadata = {'lote': uuid4().hex, 'origem': 'Cadastro de justificativas', 'nome': row['nome'],
                                             'cargo': row['cargo'], 'motivo': reason, 'bloco': event.get('titulo', '')}
            return events.api_conductor(child, event_id)
        if action in {'editar', 'excluir'}:
            return manage(request, event, action, actor)
        if action in {'previa', 'blocos'}:
            upload = request.FILES.get('arquivo')
            if not upload:
                raise ValueError('Selecione o arquivo de justificativas para conferir.')
            rows, source = read_upload(upload), Path(upload.name).name
            if not rows:
                raise ValueError('Nenhum registro legível encontrado. Confira os cabeçalhos Nome, Comum, Cargo e Motivo.')
            choices = blocks(rows)
            chosen = request.POST.get('bloco', '')
            if action == 'blocos' or (len(choices) > 1 and not chosen):
                return JsonResponse({'blocos': choices})
            if chosen and chosen not in {item['id'] for item in choices}:
                raise ValueError('O bloco selecionado não pertence a esta origem. Consulte os blocos novamente.')
            chosen = chosen or choices[0]['id']
            rows = [row for row in rows if block_key(row)[0] == chosen]
            result = reconcile(rows, common_catalog(), events._registry(), event['data_evento'])
            token = uuid4().hex
            cache.set(f'event-justifications:{actor}:{event_id}:{token}', {'rows': result, 'source': source, 'block': next(item['nome'] for item in choices if item['id'] == chosen)}, 1800)
            return JsonResponse({'token': token, 'rows': result, 'ignorados': len(rows) - len(result)})
        if action != 'confirmar':
            return JsonResponse({'error': 'Operação inválida.'}, status=404)
        raw = json.loads(request.body or '{}')
        key = f'event-justifications:{actor}:{event_id}:{raw.get("token", "")}'
        preview = cache.get(key)
        if not preview or raw.get('conferido') is not True:
            raise ValueError('Confira a prévia; se expirou, importe novamente.')
        # Refaz identificação no servidor para não gravar um cadastro alterado desde a prévia.
        rows = reconcile(preview['rows'], common_catalog(), events._registry(), event['data_evento'])
        existing = {(r['comum_chave'], normalized_name(
            r.get('encarregado_nome') or metadata(r.get('observacoes')).get('nome'))): r
            for r in events._read('musica_evento_encarregados', evento_id=f'eq.{event_id}', order='id.asc')}
        saved = updated = skipped = 0
        for row in rows:
            if row['problema']:
                skipped += 1
                continue
            was_existing = (row['comum_chave'], normalized_name(row['nome'])) in existing
            payload = {'comum_chave': row['comum_chave'], 'situacao': 'JUSTIFICOU',
                       'observacoes': f'Importação {preview["source"]}: {row.get("nome", "")} · {row.get("motivo", "Justificativa recebida")}'[:500]}
            payload['encarregado_nome'] = row['nome']
            child = copy(request)
            child._body = json.dumps(payload).encode('utf-8')
            child._justification_metadata = {'lote': raw['token'], 'origem': preview['source'],
                                             'nome': row.get('nome', ''), 'cargo': row.get('cargo', ''),
                                             'motivo': row.get('motivo') or 'Justificativa recebida', 'bloco': preview.get('block', '')}
            response = events.api_conductor(child, event_id)
            if response.status_code != 200:
                written = saved + updated
                return JsonResponse({'error': f'{written} justificativa(s) gravada(s), sendo {saved} nova(s) e {updated} atualizada(s), antes da interrupção. '
                                               + json.loads(response.content).get('error', 'Falha ao salvar.')},
                                    status=response.status_code)
            if was_existing:
                updated += 1
            else:
                saved += 1
        return JsonResponse({'gravados': saved + updated, 'novos': saved, 'atualizados': updated,
                             'preservados': skipped,
                             'encarregados_reconhecidos': sum(
                                 len(row.get('encarregados_identificados', []))
                                 for row in rows if not row['problema'])})
    except (ValueError, TypeError, csv.Error) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except (BadZipFile, PdfReadError, UnidentifiedImageError):
        return JsonResponse({'error': 'Arquivo inválido ou danificado. Exporte novamente e confira o formato.'}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível carregar ou salvar as justificativas deste evento. Tente novamente.'}, status=502)


def manage(request, event, action, actor_id):
    """Uma alteração por conjunto, sempre limitada ao evento, ids e situação conferidos."""
    from django.conf import settings
    from .access_control import service_headers
    from uuid import UUID
    raw = json.loads(request.body or '{}')
    ids = raw.get('ids')
    if not isinstance(ids, list) or not ids or len(ids) > 200:
        raise ValueError('Selecione entre 1 e 200 justificativas deste evento.')
    if any(':' in str(value) for value in ids):
        return manage_grouped(request, event, action, actor_id, raw)
    ids = list({str(UUID(str(value))) for value in ids})
    rows = events._read('musica_evento_encarregados', evento_id='eq.' + event['id'],
                        id='in.(' + ','.join(ids) + ')', situacao='eq.JUSTIFICOU', order='id.asc')
    if {r['id'] for r in rows if r.get('evento_id') == event['id'] and r.get('situacao') == 'JUSTIFICOU'} != set(ids):
        raise ValueError('A seleção contém justificativas de outro evento ou registros já alterados. Atualize a lista.')
    lot = raw.get('lote')
    if lot and any(metadata(r.get('observacoes')).get('lote') != lot for r in rows):
        raise ValueError('A seleção contém justificativas de outro lote.')
    profile = request.session.get('user_profile') or {}
    actor = profile.get('full_name') or profile.get('nome') or profile.get('name') or profile.get('email')
    if not actor:
        return JsonResponse({'error': 'Entre novamente para identificar o responsável.'}, status=401)
    reason = str(raw.get('motivo') or '').strip()
    if action == 'editar' and (not reason or len(reason) > 500):
        raise ValueError('Informe um motivo de até 500 caracteres.')
    person_name = raw.get('nome')
    if action == 'editar' and person_name is not None:
        if len(rows) != 1 or not isinstance(person_name, str) or not person_name.strip() or len(person_name) > 180:
            raise ValueError('Altere o nome individualmente, usando até 180 caracteres.')
        candidate = {'nome': person_name.strip(), 'comum': rows[0]['comum_chave'],
                     'municipio': rows[0].get('municipio'), 'cargo': 'Encarregado Local'}
        checked = reconcile([candidate], common_catalog(), events._registry(), event['data_evento'])
        if not checked or checked[0]['problema']:
            raise ValueError('O nome não corresponde a um encarregado local cadastrado nesta comum.')
        duplicate = events._read('musica_evento_encarregados', evento_id='eq.' + event['id'],
                                 comum_chave='eq.' + rows[0]['comum_chave'])
        if any(row['id'] not in ids and normalized_name(
                row.get('encarregado_nome') or metadata(row.get('observacoes')).get('nome'))
                == normalized_name(checked[0]['nome']) for row in duplicate):
            raise ValueError('Este encarregado já possui uma justificativa neste evento e comum.')
    # Metadata differs per row; each PATCH retains the event and original updated_at as a concurrency check.
    changed = 0
    for row in rows:
        info = metadata(row.get('observacoes'))
        if action == 'editar':
            if person_name is not None:
                info['nome'] = person_name.strip()
            notes = pack_metadata({**info, 'motivo': reason}) if info else reason
            payload = {'observacoes': notes}
            if person_name is not None:
                payload['encarregado_nome'] = checked[0].get('nome') or person_name.strip()
        else:
            payload = {'situacao': 'NAO_INFORMADO', 'local_id': None,
                       'observacoes': pack_metadata({**info, 'motivo': display_note(row.get('observacoes')), 'excluida': True})}
        payload.update(updated_by_user_id=str(actor_id), updated_by_name=actor)
        params = {'id': 'eq.' + row['id'], 'evento_id': 'eq.' + event['id'], 'situacao': 'eq.JUSTIFICOU'}
        if row.get('updated_at'):
            params['updated_at'] = 'eq.' + row['updated_at']
        try:
            response = requests.patch(settings.SUPABASE_URL + '/rest/v1/musica_evento_encarregados',
                                      headers=service_headers('return=representation'), params=params, json=payload, timeout=15)
            response.raise_for_status()
        except requests.RequestException:
            return JsonResponse({'error': f'{changed} justificativa(s) alterada(s) antes da interrupção. Atualize a lista para conferir e repita apenas as restantes.'}, status=502)
        if not response.json():
            return JsonResponse({'error': f'{changed} alteradas. Outro usuário modificou a seleção. Atualize a lista.'}, status=409)
        changed += 1
        events._invalidate_annual()
    return JsonResponse({'alterados': changed})


def manage_grouped(request, event, action, actor_id, raw):
    """Edita cada pessoa de registros legados por comum sem atingir seus irmãos."""
    from django.conf import settings
    from .access_control import service_headers
    from uuid import UUID
    selections = {}
    for value in set(map(str, raw['ids'])):
        key, separator, suffix = value.partition(':')
        key = str(UUID(key))
        if separator and (not suffix.isdigit() or int(suffix) > 199):
            raise ValueError('Identificação individual inválida. Atualize a lista.')
        selections.setdefault(key, set()).add(int(suffix) if separator else None)
    rows = events._read('musica_evento_encarregados', evento_id='eq.' + event['id'],
                        id='in.(' + ','.join(selections) + ')', situacao='eq.JUSTIFICOU', order='id.asc')
    if {row['id'] for row in rows if row.get('evento_id') == event['id'] and row.get('situacao') == 'JUSTIFICOU'} != set(selections):
        raise ValueError('Seleção alterada ou fora deste evento. Atualize a lista.')
    actor = request.session.get('user_profile') or {}
    actor = actor.get('full_name') or actor.get('nome') or actor.get('name') or actor.get('email')
    if not actor:
        return JsonResponse({'error': 'Entre novamente para identificar o responsável.'}, status=401)
    reason = str(raw.get('motivo') or '').strip()
    if action == 'editar' and (not reason or len(reason) > 500):
        raise ValueError('Informe um motivo de até 500 caracteres.')
    if raw.get('nome') is not None and len(set(map(str, raw['ids']))) != 1:
        raise ValueError('Altere o nome individualmente.')
    plans = []
    for row in rows:
        info = metadata(row.get('observacoes'))
        if raw.get('lote') and info.get('lote') != raw['lote']:
            raise ValueError('A seleção contém justificativas de outro lote.')
        people = info.get('pessoas')
        grouped = isinstance(people, list) and len(people) > 1
        if not grouped:
            people = [{'nome': row.get('encarregado_nome') or info.get('nome', ''),
                       'motivo': display_note(row.get('observacoes')), 'situacao': row['situacao']}]
        indices = selections[row['id']]
        if grouped and None in indices or not grouped and indices != {None}:
            raise ValueError('Selecione a pessoa pela lista atualizada.')
        indices = {0} if not grouped else indices
        for index in indices:
            if index >= len(people) or people[index].get('excluida') or people[index].get('situacao', row['situacao']) != 'JUSTIFICOU':
                raise ValueError('A justificativa individual já foi alterada. Atualize a lista.')
            person = people[index]
            if action == 'editar':
                if raw.get('nome') is not None:
                    name = raw['nome']
                    if not isinstance(name, str) or not name.strip() or len(name) > 180:
                        raise ValueError('Informe um nome válido de até 180 caracteres.')
                    checked = reconcile([{'nome': name, 'comum': row['comum_chave'],
                                          'municipio': row['municipio'], 'cargo': 'Encarregado Local'}],
                                        common_catalog(), events._registry(), event['data_evento'])
                    if not checked or checked[0]['problema']:
                        raise ValueError('Nome não confirmado no cadastro desta comum.')
                    name = checked[0]['nome']
                    if any(i != index and not other.get('excluida') and normalized_name(other['nome']) == normalized_name(name)
                           for i, other in enumerate(people)):
                        raise ValueError('Este encarregado já possui justificativa nesta comum.')
                    person['nome'] = name
                person['motivo'] = reason
            else:
                person.update(excluida=True, situacao='NAO_INFORMADO')
        active = [p for p in people if not p.get('excluida')]
        info.update(pessoas=people, nome=' / '.join(p['nome'] for p in active),
                    motivo=' | '.join(dict.fromkeys(p.get('motivo', '') for p in active)))
        payload = {'observacoes': pack_metadata(info), 'situacao': 'JUSTIFICOU' if active else 'NAO_INFORMADO',
                   'local_id': None, 'updated_by_user_id': str(actor_id), 'updated_by_name': actor}
        params = {'id': 'eq.' + row['id'], 'evento_id': 'eq.' + event['id'], 'situacao': 'eq.JUSTIFICOU'}
        if row.get('updated_at'):
            params['updated_at'] = 'eq.' + row['updated_at']
        plans.append((payload, params, len(indices)))
    changed = 0
    for payload, params, count in plans:
        try:
            response = requests.patch(settings.SUPABASE_URL + '/rest/v1/musica_evento_encarregados',
                                      headers=service_headers('return=representation'), params=params, json=payload, timeout=15)
            response.raise_for_status()
        except requests.RequestException:
            return JsonResponse({'error': f'{changed} justificativas alteradas. Atualize a lista antes de repetir.'}, status=502)
        if not response.json():
            return JsonResponse({'error': 'Outro usuário modificou a seleção. Atualize a lista.'}, status=409)
        changed += count
        events._invalidate_annual()
    return JsonResponse({'alterados': changed})
