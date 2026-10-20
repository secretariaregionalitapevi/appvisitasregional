"""Espelha sob demanda aulas citadas nos logs, inclusive as abertas hoje."""
import json
import re
from datetime import datetime, timezone

import requests
from django.conf import settings

from .access_control import service_headers
from .sam_class_mirror import BASE_URL, fetch_text, fingerprint, norm, parse_attendance, parse_class_detail, parse_class_row


def _get(table, params, limit=5000):
    response = requests.get(f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers(),
                            params={**params, "limit": limit}, timeout=30)
    response.raise_for_status()
    return response.json()


def _upsert(table, rows, conflict):
    if not rows:
        return []
    response = requests.post(
        f"{settings.SUPABASE_URL}/rest/v1/{table}",
        headers=service_headers("resolution=merge-duplicates,return=representation"),
        params={"on_conflict": conflict}, json=rows, timeout=60,
    )
    response.raise_for_status()
    return response.json()


def mirror_referenced_classes(session, events):
    class_ids = {str((event.get("parsed_refs") or {}).get("class_id")) for event in events
                 if (event.get("parsed_refs") or {}).get("class_id")}
    if not class_ids:
        return {"classes": 0, "attendance": 0}
    existing = _get("sam_gem_classes", {"select": "source_id", "source_id": "in.(" + ",".join(class_ids) + ")"})
    class_ids -= {str(row.get("source_id")) for row in existing}
    if not class_ids:
        return {"classes": 0, "attendance": 0}

    states = _get("sam_student_sync_state", {"select": "source_key,source_name,source_common,source_instrument,aluno_id",
                                               "aluno_id": "not.is.null"})
    by_source = {str(row.get("source_key")): row for row in states}
    by_name = {}
    for row in states:
        by_name.setdefault(norm(row.get("source_name")), []).append(row.get("aluno_id"))
    page, class_count, attendance_count = session.scraper.page, 0, 0
    for source_id in sorted(class_ids, key=int):
        payload = {"draw": "1", "start": "0", "length": "5", "search[value]": source_id,
                   "order[0][column]": "4", "order[0][dir]": "desc"}
        listing = json.loads(fetch_text(page, f"{BASE_URL}/aulas_abertas/listagem", "POST", payload))
        candidates = [parse_class_row(row) for row in listing.get("data") or []]
        item = next((row for row in candidates if str(row.get("source_id")) == source_id), None)
        if not item or not item.get("turma_source_id"):
            continue
        now = datetime.now(timezone.utc).isoformat()
        group_payload = {"source_id": int(item["turma_source_id"]), "congregacao": item.get("congregacao"),
                         "curso": item.get("curso"), "turma": item.get("turma"), "ativo": True,
                         "source_payload": dict(item), "last_seen_at": now, "synced_at": now}
        group_payload["source_hash"] = fingerprint({k: v for k, v in group_payload.items() if k not in {"last_seen_at", "synced_at", "source_hash"}})
        preserved_groups = _get("sam_gem_groups", {"select": "*", "source_id": f"eq.{item['turma_source_id']}"})
        group = preserved_groups[0] if preserved_groups else _upsert("sam_gem_groups", [group_payload], "source_id")[0]
        detail = parse_class_detail(fetch_text(page, f"{BASE_URL}/aulas_abertas/visualizar_aula/{source_id}"))
        class_payload = {**item, **detail, "turma_id": group["id"], "source_payload": {**item, **detail},
                         "last_seen_at": now, "synced_at": now}
        class_payload["source_hash"] = fingerprint({k: v for k, v in class_payload.items() if k not in {"last_seen_at", "synced_at", "source_hash"}})
        saved = _upsert("sam_gem_classes", [class_payload], "source_id")[0]
        records = parse_attendance(fetch_text(page, f"{BASE_URL}/aulas_abertas/visualizar_frequencias/{source_id}/{item['turma_source_id']}"))
        attendance_rows, enrollment_rows = [], []
        for record in records:
            member_match = re.search(r"\d+", str(record.get("source_member_id") or ""))
            frequency_match = re.search(r"\d+", str(record.get("source_frequency_id") or ""))
            if not member_match:
                continue
            member_id = member_match.group(0)
            state = by_source.get(member_id) or {}
            named = by_name.get(norm(record.get("nome_aluno"))) or []
            aluno_id = state.get("aluno_id") or (named[0] if len(named) == 1 else None)
            attendance_rows.append({**record, "source_member_id": int(member_id),
                                    "source_frequency_id": int(frequency_match.group(0)) if frequency_match else None,
                                    "aula_id": saved["id"], "aluno_id": aluno_id,
                                    "last_seen_at": now, "synced_at": now})
            enrollment = {"turma_id": group["id"], "source_member_id": int(member_id), "aluno_id": aluno_id,
                          "nome_aluno": record.get("nome_aluno"),
                          "congregacao": state.get("source_common") or item.get("congregacao"),
                          "instrumento": state.get("source_instrument"), "ativo": True,
                          "last_seen_at": now, "synced_at": now}
            enrollment["source_hash"] = fingerprint({k: v for k, v in enrollment.items() if k not in {"last_seen_at", "synced_at", "source_hash"}})
            enrollment_rows.append(enrollment)
        _upsert("sam_gem_attendance", attendance_rows, "aula_id,source_member_id")
        _upsert("sam_gem_enrollments", enrollment_rows, "turma_id,source_member_id")
        class_count += 1
        attendance_count += len(attendance_rows)
    return {"classes": class_count, "attendance": attendance_count}
