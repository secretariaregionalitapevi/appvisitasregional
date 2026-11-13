"""Two-phase, scope-checked exam imports with retryable synchronization."""
import hashlib
import json
import uuid
import subprocess
from zipfile import BadZipFile
from pypdf.errors import PdfReadError

import requests
from django.core.cache import cache
from django.http import JsonResponse

from . import music_exams as exams
from .exam_import import read_date, read_document, exam_kind
from .exam_identity import common_code, resolve_student, ranked_students, new_student_plan, save_identity
from .access_control import common_catalog

KINDS = {'OFICIALIZAÇÃO', 'CULTO OFICIAL', 'RJM', 'TESTE EMERGENCIAL', 'TROCA DE INSTRUMENTO'}


def owner(request):
    if not request.session.get('exam_import_owner'):
        request.session['exam_import_owner'] = uuid.uuid4().hex
    return hashlib.sha256((request.session['exam_import_owner'] + json.dumps(request.session.get('user_profile') or {}, sort_keys=True)).encode()).hexdigest()


def row_payload(row, choice, students, events, request):
    student = students.get(str(choice.get('aluno_id')))
    if not student:
        raise ValueError('Selecione um aluno do seu escopo.')
    if common_code(row['comum']) != common_code(student.get('comum_congregacao')):
        raise ValueError('A comum do documento difere do cadastro do aluno. Corrija o cadastro ou o documento.')
    kind = choice.get('tipo_exame') or row.get('tipo_exame')
    if kind not in KINDS:
        raise ValueError('Selecione uma modalidade válida.')
    organist = 'ORGANISTA' in exams.norm(student.get('cargo_ministerio')) or exams.norm(student.get('instrumento')) in {'ORGAO', 'ORGANISTA'}
    if not organist and kind in {'RJM', 'TESTE EMERGENCIAL'}:
        raise ValueError('RJM e emergência são exclusivos para organistas; confira o cadastro.')
    result = choice.get('resultado') or row.get('resultado')
    if result not in exams.RESULTS:
        raise ValueError('Resultado inválido.')
    date = read_date(choice.get('data_exame') or row.get('data_exame'))
    if not date:
        raise ValueError('Informe a data do exame.')
    event_id = choice.get('agenda_evento_id')
    possible = [e for e in events if e['data'] == date and exams.event_matches_municipality(e, student.get('municipio'))
                and (('ORGANISTA' in exams.norm(e['titulo'])) if organist else ('MUSICO' in exams.norm(e['titulo'])))]
    event = next((e for e in possible if e['id'] == event_id), None) if event_id else (possible[0] if len(possible) == 1 else None)
    if event_id and not event:
        raise ValueError('Evento incompatível com data, município ou categoria.')
    if not event and possible:
        raise ValueError('Há mais de um evento nesta data. Escolha o evento correspondente.')
    if not event and not choice.get('historico_sem_agenda'):
        raise ValueError('Nenhum evento compatível. Confirme o registro histórico sem agenda ou corrija a data.')
    payload = dict(aluno_id=student['id'], nome_aluno=student.get('nome_aluno'),
                   registro_msa=student.get('registro_msa'), municipio=student.get('municipio'),
                   comum=student.get('comum_congregacao'), instrumento=student.get('instrumento'),
                   categoria=student.get('cargo_ministerio'), data_exame=date, tipo_exame=kind,
                   resultado=result, encarregado_local=row.get('encarregado_local') or None,
                   lancado_por=exams.actor(request), origem='IMPORTACAO')
    if event:
        payload.update(agenda_evento_id=event['id'], agenda_evento_data=event['data'],
                       agenda_evento_titulo=event['titulo'], agenda_evento_hora=event.get('hora') or None,
                       agenda_evento_url=event['url'])
    payload['chave_idempotencia'] = exams.idempotency_key(payload)
    return student, payload


def import_exams(request):
    if not exams.can_open_module(request):
        return exams.denied()
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido.'}, status=405)
    try:
        if request.FILES.get('arquivo'):
            rows = read_document(request.FILES['arquivo'])
            if not rows:
                raise ValueError('Nenhuma linha reconhecida. Use colunas Nome, Comum, Tipo, Data e Resultado, ou blocos por etapa.')
            if len(rows) > 500:
                raise ValueError('Importe no máximo 500 resultados por lote.')
            for row in rows:
                if 'ORGANISTA' in exams.norm(request.FILES['arquivo'].name) or row.get('tipo_exame') == 'RJM':
                    row['categoria'] = 'ORGANISTA'
            students = exams.visible_students(request, {common_code(r['comum']) for r in rows})
            for index, row in enumerate(rows):
                student = resolve_student(row, students)
                ranked = ranked_students(row, students)
                row['candidates'] = [{'id':str(s['id']), 'nome':s.get('nome_aluno'), 'comum':s.get('comum_congregacao'),
                                      'municipio':s.get('municipio'), 'score':round(score*100)} for score,s in ranked[:8]]
                row['match_score'] = next((c['score'] for c in row['candidates'] if student and c['id'] == str(student['id'])), None)
                row['nome_cadastro'] = student.get('nome_aluno') if student else ''
                row['criar_cadastro'] = not ranked
                row.update(linha=index, aluno_id=str(student['id']) if student else '',
                           municipio=student.get('municipio') if student else '',
                           grupo=exams.regional_group(student.get('municipio')) if student else '')
            token = uuid.uuid4().hex
            cache.set('exam-import:' + token, {'owner': owner(request), 'rows': rows, 'filename': request.FILES['arquivo'].name}, 1800)
            try:
                events = exams.agenda_events()
                warning = 'Fotografias e documentos digitalizados exigem conferência: o reconhecimento pode omitir linhas ou trocar letras.' if request.FILES['arquivo'].name.lower().endswith(('.jpg','.jpeg','.png','.webp','.tif','.tiff','.bmp','.pdf')) else ''
            except requests.RequestException:
                events = []
                warning = 'Agenda indisponível. Tente novamente antes de confirmar ou identifique explicitamente registros históricos.'
            return JsonResponse({'token': token, 'items': rows, 'events': events, 'warning': warning})
        data = json.loads(request.body or '{}')
        token = str(data.get('token') or '')
        batch = cache.get('exam-import:' + token)
        if not batch or batch['owner'] != owner(request):
            raise ValueError('Prévia expirada. Envie o arquivo novamente.')
        choices = data.get('items')
        if not isinstance(choices, list) or not choices or len(choices) > 500:
            raise ValueError('Selecione as linhas que deseja importar.')
        student_list = exams.visible_students(request, {common_code(r['comum']) for r in batch['rows']})
        students = {str(s['id']): s for s in student_list}
        catalog = common_catalog() if any(c.get('criar_cadastro') for c in choices) else []
        try:
            events = exams.agenda_events()
        except requests.RequestException:
            if not all(c.get('historico_sem_agenda') for c in choices):
                raise ValueError('Agenda indisponível. Tente novamente.')
            events = []
        prepared, errors, keys = [], [], set()
        existing_rows = exams.fetch_rows(request, False)
        existing = {r['chave_idempotencia']: r for r in existing_rows}
        for choice in choices:
            try:
                index = int(choice['linha'])
                if index < 0 or index >= len(batch['rows']):
                    raise ValueError('Linha inválida.')
                row = batch['rows'][index]
                creating = False
                if choice.get('criar_cadastro'):
                    matched = resolve_student(row, student_list)
                    if matched:
                        choice = dict(choice, aluno_id=str(matched['id']))
                    elif ranked_students(row, student_list):
                        raise ValueError('Existem cadastros semelhantes nesta comum. Escolha o cadastro para evitar duplicação.')
                    else:
                        candidate = new_student_plan(row, choice, request, catalog)
                        students[candidate['id']] = candidate
                        choice = dict(choice, aluno_id=candidate['id'])
                        creating = True
                student, payload = row_payload(row, choice, students, events, request)
                if not creating and choice.get('atualizar_nome') and not any(str(s['id']) == str(student['id']) for _,s in ranked_students(row, [student])):
                    raise ValueError('A correção de nome exige similaridade de pelo menos 75% e o mesmo primeiro nome e comum.')
                payload['observacoes'] = None
                key = payload['chave_idempotencia']
                if key in keys:
                    continue
                keys.add(key)
                old = existing.get(key)
                if not old:
                    same = [r for r in existing_rows if str(r.get('aluno_id')) == str(payload['aluno_id'])
                            and r.get('data_exame') == payload['data_exame']
                            and exam_kind(r.get('tipo_exame')) == payload['tipo_exame']]
                    if len(same) > 1:
                        raise ValueError('Há múltiplos exames desta etapa na data. Revise o histórico antes de importar.')
                    old = same[0] if same else None
                if old:
                    payload['chave_idempotencia'] = old['chave_idempotencia']
                    payload['observacoes'] = exams.clean_exam_notes(old.get('observacoes')) or None
                if old and old.get('resultado') != payload['resultado'] and old.get('resultado') != 'AGENDADO':
                    raise ValueError('Já existe exame nesta data com outro resultado. Edite o registro existente.')
                prepared.append((index, student, payload, old, choice, creating))
            except (ValueError, KeyError, TypeError) as exc:
                errors.append({'linha': choice.get('linha'), 'error': str(exc)})
        if errors:
            return JsonResponse({'error': 'Revise as linhas indicadas. Nenhum registro foi gravado.', 'errors': errors}, status=400)
        if data.get('validar_apenas'):
            return JsonResponse({'ok':True, 'validados':len(prepared)})
        lock = 'exam-import-lock:' + token
        if not cache.add(lock, True, 1800):
            return JsonResponse({'error': 'Este lote já está em processamento.'}, status=409)
        imported, duplicates, failures, created, renamed = 0, 0, [], 0, 0
        try:
            if len(prepared)>1:
                from .exam_import_batch import commit_prepared
                try:
                    return JsonResponse(commit_prepared(prepared,batch['rows']))
                except requests.RequestException:
                    return JsonResponse({'ok':False,'error':'Não foi possível concluir todas as gravações do lote. Parte dos dados pode ter sido salva; repita a confirmação para concluir sem duplicar.'},status=502)
            # Each record is retryable, including its shared totals and student level.
            for index, student, payload, old, choice, creating in prepared:
                try:
                    previous_name = student.get('nome_aluno')
                    saved_student = save_identity(student, batch['rows'][index], choice, creating)
                    student.update(saved_student)
                    created += int(creating)
                    renamed += int(previous_name != student.get('nome_aluno') and not creating)
                    payload['nome_aluno'] = student.get('nome_aluno')
                    if not old:
                        payload['chave_idempotencia'] = exams.idempotency_key(payload)
                    if old and old.get('resultado') == 'AGENDADO' and payload['resultado'] != 'AGENDADO':
                        item = exams.save_exam(dict(old, **payload), old['id'])
                    else:
                        item = old or exams.save_exam(payload)
                    imported += int(not bool(old))
                    duplicates += int(bool(old))
                    exams.sync_shared_exam(item)
                    exams.update_student_stage(student, item)
                    stage = exams.approved_stage(item)
                    if stage:
                        from .gem import _milestones
                        if _milestones(student.get('nivel'))[stage[0]]['status'] == 'future':
                            student['nivel'] = stage[2]
                except (requests.RequestException, ValueError):
                    failures.append({'linha': index, 'error': 'Falha ao gravar ou sincronizar. Reenvie a confirmação para concluir sem duplicar.'})
        finally:
            cache.delete(lock)
        return JsonResponse({'ok': not failures, 'importados': imported, 'duplicados': duplicates, 'cadastrados':created,'nomes_atualizados':renamed,'errors': failures})
    except (ValueError, KeyError, TypeError, OSError, ImportError, BadZipFile, PdfReadError, subprocess.TimeoutExpired, RuntimeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível consultar o banco. Tente novamente.'}, status=502)
