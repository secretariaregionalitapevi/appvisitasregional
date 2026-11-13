"""Match exam identities within a common and preserve the existing student ID."""
import re
import uuid
from difflib import SequenceMatcher
from . import music_exams as exams
from .access_control import user_scope, can_access, service_headers
from django.conf import settings
import requests

PARTICLES = {'DA', 'DE', 'DO', 'DAS', 'DOS', 'E'}


def common_code(value):
    match = re.search(r'BR-\d{2}-\d+', exams.norm(value))
    return match.group() if match else exams.norm(value)


def name_key(value):
    return ' '.join(w for w in re.findall(r'[A-Z]+', exams.norm(value)) if w not in PARTICLES)


def organist(student):
    return 'ORGANISTA' in exams.norm(student.get('cargo_ministerio')) or exams.norm(student.get('instrumento')) in {'ORGAO', 'ORGANISTA'}


def ranked_students(row, students):
    wanted = name_key(row['nome'])
    first = wanted.split()[:1]
    ranked = []
    for student in students:
        if common_code(student.get('comum_congregacao')) != common_code(row['comum']):
            continue
        other = name_key(student.get('nome_aluno'))
        if row.get('categoria') == 'ORGANISTA' and not organist(student) and other != wanted:
            continue
        # A shared surname alone must not link Raquel to Miguel or Helen to Ricardo.
        if not wanted or other.split()[:1] != first:
            continue
        score = SequenceMatcher(None, wanted, other, autojunk=False).ratio()
        if score >= .75:
            ranked.append((score, student))
    return sorted(ranked, key=lambda x: (-x[0], str(x[1]['id'])))


def resolve_student(row, students):
    ranked = ranked_students(row, students)
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < .08:
        return None
    return ranked[0][1]


def new_student_plan(row, choice, request, catalog):
    code = common_code(row['comum'])
    matches = [r for r in catalog if common_code(r.get('comum')) == code]
    locations = {(r.get('comum'), r.get('cidade')) for r in matches}
    if len(locations) != 1:
        raise ValueError('Comum não identificada de forma única no catálogo. Corrija o código antes de cadastrar.')
    common, city = locations.pop()
    if not city or not can_access(user_scope(request), {'comum': common, 'municipio': city}):
        raise ValueError('O novo cadastro está fora do seu escopo.')
    name = ' '.join(row['nome'].upper().split())
    if len(name_key(name).split()) < 2:
        raise ValueError('Confira o nome completo antes de cadastrar.')
    category = choice.get('categoria') or row.get('categoria')
    instrument = 'ÓRGÃO' if category == 'ORGANISTA' else (choice.get('instrumento') or row.get('instrumento'))
    if category not in {'ORGANISTA', 'MÚSICO'} or not instrument:
        raise ValueError('Informe categoria e instrumento do novo aluno.')
    student_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'ccb-exam-student:' + code + ':' + name_key(name)))
    # Missing personal information and consent are never invented.
    return dict(id=student_id, nome_aluno=name, comum_congregacao=common, municipio=city,
                cargo_ministerio=category, instrumento=instrument, nivel='CANDIDATO(A)',
                lancado_por=exams.actor(request), consentimento_lgpd=False)


def save_identity(student, row, choice, creating=False, update_cache=True):
    url = f'{settings.SUPABASE_URL}/rest/v1/musica_acompanhamento_aluno'
    if creating:
        response = requests.post(url, params={'on_conflict':'id'},
            headers=service_headers('resolution=ignore-duplicates,return=representation'), json=student, timeout=(5,20))
        response.raise_for_status()
        rows = response.json()
        if not rows:
            response = requests.get(url, headers=service_headers(), params={'select':'*','id':'eq.'+student['id']}, timeout=(5,20))
            response.raise_for_status()
            rows = response.json()
        if not rows:
            raise ValueError('Não foi possível recuperar o novo cadastro.')
        student = rows[0]
    elif choice.get('atualizar_nome') and exams.norm(student.get('nome_aluno')) != exams.norm(row['nome']):
        response = requests.patch(url, headers=service_headers('return=representation'),
            params={'id':'eq.'+str(student['id'])}, json={'nome_aluno':' '.join(row['nome'].upper().split())}, timeout=(5,20))
        response.raise_for_status()
        student = (response.json() or [dict(student, nome_aluno=row['nome'])])[0]
    if update_cache:
        from .gem import _update_students_cache
        _update_students_cache(student)
    return student
