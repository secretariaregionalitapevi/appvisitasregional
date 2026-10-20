"""Resolve IDs precarios dos logs SAM para pessoas, aulas e turmas legiveis."""
from collections import defaultdict

import requests
from django.conf import settings

from .access_control import service_headers


def _get(table, params, limit=5000):
    response = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers(),
        params={**params, "limit": limit}, timeout=(3.05, 30),
    )
    response.raise_for_status()
    return response.json()


def _in(values):
    clean = [str(value) for value in values if value not in (None, "")]
    return "in.(" + ",".join(clean) + ")" if clean else None


def _group_view(group, members):
    if not group:
        return None
    return {
        "source_id": group.get("source_id"), "name": group.get("turma") or group.get("curso") or "Turma SAM",
        "course": group.get("curso"), "congregation": group.get("congregacao"),
        "start_date": group.get("data_inicio"), "end_date": group.get("data_termino"),
        "schedule": group.get("dia_horario"), "active": group.get("ativo"),
        "detected_at": group.get("first_seen_at"), "last_seen_at": group.get("last_seen_at"),
        "enrolled_count": group.get("matriculados") if group.get("matriculados") is not None else len(members),
        "members": [{"source_member_id": row.get("source_member_id"), "name": row.get("nome_aluno"),
                     "instrument": row.get("instrumento"), "congregation": row.get("congregacao"),
                     "active": row.get("ativo")} for row in members],
    }


def search_event_reference_ids(search):
    """Traduz nome de aluno/turma nos IDs que aparecem no texto dos logs."""
    value = str(search or "").strip().replace("*", "")[:100]
    if len(value) < 2:
        return []
    states = _get("sam_student_sync_state", {"select": "source_key,aluno_id", "source_name": f"ilike.*{value}*"}, 100)
    enrollments = _get("sam_gem_enrollments", {"select": "source_member_id,turma_id,aluno_id",
                                                "nome_aluno": f"ilike.*{value}*"}, 100)
    member_ids = {str(row.get("source_key")) for row in states if row.get("source_key")}
    member_ids.update(str(row.get("source_member_id")) for row in enrollments if row.get("source_member_id"))
    group_uuids = {row.get("turma_id") for row in enrollments if row.get("turma_id")}
    ids = set(member_ids)
    attendance = _get("sam_gem_attendance", {"select": "source_member_id,source_frequency_id,aula_id",
                                               "source_member_id": _in(member_ids)}, 1000) if member_ids else []
    ids.update(str(row.get("source_frequency_id")) for row in attendance if row.get("source_frequency_id"))
    class_uuids = {row.get("aula_id") for row in attendance if row.get("aula_id")}
    classes = _get("sam_gem_classes", {"select": "id,source_id,turma_id", "id": _in(class_uuids)}, 500) if class_uuids else []
    ids.update(str(row.get("source_id")) for row in classes if row.get("source_id"))
    group_uuids.update(row.get("turma_id") for row in classes if row.get("turma_id"))
    groups = _get("sam_gem_groups", {"select": "id,source_id", "id": _in(group_uuids)}, 500) if group_uuids else []
    ids.update(str(row.get("source_id")) for row in groups if row.get("source_id"))
    return sorted(ids)[:200]


def enrich_events(events):
    """Anexa uma resolucao humana sem substituir a evidencia original."""
    attendance_ids, member_ids, class_ids, group_ids, student_ids = set(), set(), set(), set(), set()
    for event in events:
        refs = event.get("parsed_refs") or {}
        attendance_ids.update(filter(None, (refs.get("attendance_id"), refs.get("enrollment_id"))))
        member_ids.update(filter(None, (refs.get("student_id"), refs.get("member_id"))))
        class_ids.update(filter(None, (refs.get("class_id"),)))
        group_ids.update(filter(None, (refs.get("group_id"),)))
        student_ids.update(filter(None, (refs.get("student_id"),)))

    attendance = []
    clauses = []
    if attendance_ids:
        clauses.append("source_frequency_id." + _in(attendance_ids))
    if member_ids:
        clauses.append("source_member_id." + _in(member_ids))
    if clauses:
        attendance = _get("sam_gem_attendance", {"select": "*", "or": "(" + ",".join(clauses) + ")"})
    attendance_by_frequency = {str(row.get("source_frequency_id")): row for row in attendance if row.get("source_frequency_id")}
    attendance_by_member = defaultdict(list)
    for row in attendance:
        attendance_by_member[str(row.get("source_member_id"))].append(row)

    direct_enrollments = _get(
        "sam_gem_enrollments", {"select": "*", "source_member_id": _in(member_ids)}, 1000
    ) if member_ids else []
    enrollments_by_member = defaultdict(list)
    for row in direct_enrollments:
        enrollments_by_member[str(row.get("source_member_id"))].append(row)

    class_uuids = {row.get("aula_id") for row in attendance if row.get("aula_id")}
    class_clauses = []
    if class_ids:
        class_clauses.append("source_id." + _in(class_ids))
    if class_uuids:
        class_clauses.append("id." + _in(class_uuids))
    group_uuids = {row.get("turma_id") for row in direct_enrollments if row.get("turma_id")}
    if group_uuids:
        class_clauses.append("turma_id." + _in(group_uuids))
    classes = _get("sam_gem_classes", {"select": "*", "or": "(" + ",".join(class_clauses) + ")"}) if class_clauses else []
    classes_by_source = {str(row.get("source_id")): row for row in classes}
    classes_by_id = {str(row.get("id")): row for row in classes}
    classes_by_group = defaultdict(list)
    for row in sorted(classes, key=lambda item: str(item.get("data_aula") or ""), reverse=True):
        if row.get("turma_id"):
            classes_by_group[str(row["turma_id"])].append(row)

    group_uuids.update(row.get("turma_id") for row in classes if row.get("turma_id"))
    group_clauses = []
    if group_ids:
        group_clauses.append("source_id." + _in(group_ids))
    if group_uuids:
        group_clauses.append("id." + _in(group_uuids))
    groups = _get("sam_gem_groups", {"select": "*", "or": "(" + ",".join(group_clauses) + ")"}) if group_clauses else []
    groups_by_source = {str(row.get("source_id")): row for row in groups}
    groups_by_id = {str(row.get("id")): row for row in groups}
    enrollments = _get("sam_gem_enrollments", {"select": "*", "turma_id": _in(group_uuids)}) if group_uuids else []
    enrollment_rows = []
    enrollment_keys = set()
    for row in enrollments + direct_enrollments:
        key = str(row.get("id") or f"{row.get('source_member_id')}:{row.get('turma_id')}")
        if key not in enrollment_keys:
            enrollment_keys.add(key)
            enrollment_rows.append(row)
    enrollments = enrollment_rows
    members_by_group = defaultdict(list)
    for row in enrollments:
        members_by_group[str(row.get("turma_id"))].append(row)

    states = _get("sam_student_sync_state", {"select": "source_key,source_name,source_common,source_instrument,aluno_id",
                                              "source_key": _in(student_ids)}) if student_ids else []
    states_by_source = {str(row.get("source_key")): row for row in states}
    student_uuids = {str(row.get("aluno_id")) for row in direct_enrollments + states if row.get("aluno_id")}
    try:
        method_rows = _get(
            "musica_acompanhamento_metodo",
            {"select": "id,aluno_id,data_inicio,metodo,pagina,licao,autorizado_por",
             "aluno_id": _in(student_uuids), "order": "data_inicio.desc"},
            1000,
        ) if student_uuids else []
    except requests.RequestException:
        method_rows = []
    methods_by_student = defaultdict(list)
    for row in method_rows:
        methods_by_student[str(row.get("aluno_id"))].append(row)

    enriched = []
    for original in events:
        event, refs = dict(original), original.get("parsed_refs") or {}
        attendance_row = attendance_by_frequency.get(str(refs.get("attendance_id") or refs.get("enrollment_id")))
        if not attendance_row and refs.get("student_id"):
            matches = attendance_by_member.get(str(refs["student_id"])) or []
            attendance_row = matches[0] if len(matches) == 1 else None
        class_row = classes_by_source.get(str(refs.get("class_id")))
        if not class_row and attendance_row:
            class_row = classes_by_id.get(str(attendance_row.get("aula_id")))
        group_row = groups_by_source.get(str(refs.get("group_id")))
        if not group_row and class_row:
            group_row = groups_by_id.get(str(class_row.get("turma_id")))
        state = states_by_source.get(str(refs.get("student_id")))
        student = None
        if attendance_row:
            student = {"source_member_id": attendance_row.get("source_member_id"),
                       "name": attendance_row.get("nome_aluno"), "present": attendance_row.get("presente")}
        elif state:
            student = {"source_member_id": state.get("source_key"), "name": state.get("source_name"),
                       "congregation": state.get("source_common"), "instrument": state.get("source_instrument")}
        if not student and refs.get("student_id"):
            matches = enrollments_by_member.get(str(refs["student_id"])) or []
            names = {str(row.get("nome_aluno") or "").strip() for row in matches if row.get("nome_aluno")}
            if len(names) == 1:
                match = next((row for row in matches if row.get("nome_aluno")), {})
                student = {"source_member_id": match.get("source_member_id"), "aluno_id": match.get("aluno_id"),
                           "name": next(iter(names)), "congregation": match.get("congregacao"),
                           "instrument": match.get("instrumento")}
        member_enrollments = enrollments_by_member.get(str(refs.get("student_id"))) or []
        if not group_row and member_enrollments:
            member_enrollments = sorted(
                member_enrollments,
                key=lambda row: str((classes_by_group.get(str(row.get("turma_id"))) or [{}])[0].get("data_aula") or ""),
                reverse=True,
            )
            group_row = groups_by_id.get(str(member_enrollments[0].get("turma_id")))
            if not class_row:
                group_classes = classes_by_group.get(str(member_enrollments[0].get("turma_id"))) or []
                class_row = group_classes[0] if group_classes else None
        class_view = None
        if class_row:
            class_view = {"source_id": class_row.get("source_id"), "date": class_row.get("data_aula"),
                          "start": class_row.get("inicio"), "end": class_row.get("termino"),
                          "instructor": class_row.get("instrutor_aula") or class_row.get("instrutor_responsavel"),
                          "course": class_row.get("curso"), "name": class_row.get("turma"),
                          "congregation": class_row.get("congregacao")}
        group_view = _group_view(group_row, members_by_group.get(str((group_row or {}).get("id")), []))
        student_id = str((student or {}).get("aluno_id") or (state or {}).get("aluno_id") or "")
        method_history = methods_by_student.get(student_id) or []
        if student is not None and method_history:
            student["latest_method"] = method_history[0]
        if student:
            primary_name = student.get("name")
            entity_type = "student"
        elif group_view:
            primary_name = group_view.get("name")
            entity_type = "group"
        elif class_view:
            primary_name = class_view.get("name") or class_view.get("course") or "Aula SAM"
            entity_type = "class"
        else:
            primary_name = None
            entity_type = event.get("target_type")
        event["resolution"] = {"resolved": bool(primary_name), "entity_type": entity_type,
                               "primary_name": primary_name, "student": student,
                               "class": class_view, "group": group_view,
                               "method_reference_id": refs.get("method_id"),
                               "latest_method": method_history[0] if method_history else None}
        if primary_name:
            event["target_name_snapshot"] = event.get("target_name_snapshot") or primary_name
        enriched.append(event)
    return enriched
