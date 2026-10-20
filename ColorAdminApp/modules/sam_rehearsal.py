"""Recriação local de Vila das Chácaras em SQLite. Nenhuma operação de rede."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import UUID, NAMESPACE_URL, uuid5

from . import sam_backup as backup
from .sam_history_sync import SOURCE_CONFIG

COMMON = "BR-22-2999"
CITY = "ITAPEVI"
VERSION = 1


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _member(value):
    text = str(value or "").strip()
    return str(int(text)) if text.isdigit() and int(text) > 0 else None


def _path():
    return backup.archive_dir() / "rehearsals.sqlite3"


def _connect(write=False):
    path = _path()
    if write:
        if getattr(backup.settings, "IS_PRODUCTION", False) and not getattr(backup.settings, "SAM_BACKUP_DIR", None):
            raise backup.BackupError("O ensaio exige armazenamento local persistente configurado.")
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
    else:
        if not path.is_file():
            raise backup.BackupError("Nenhum ensaio local foi criado.")
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if write:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, backup_id TEXT NOT NULL, backup_sha256 TEXT NOT NULL,
                group_id TEXT NOT NULL, common_code TEXT NOT NULL CHECK(common_code = 'BR-22-2999'),
                city TEXT NOT NULL CHECK(city = 'ITAPEVI'), created_at TEXT NOT NULL,
                version INTEGER NOT NULL, manifest TEXT NOT NULL, content_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entities (
                run_id TEXT NOT NULL REFERENCES runs(id), kind TEXT NOT NULL,
                source_id TEXT NOT NULL, target_id TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (run_id,kind,source_id), UNIQUE (run_id,target_id)
            );
            CREATE TABLE IF NOT EXISTS relations (
                run_id TEXT NOT NULL, kind TEXT NOT NULL, source_id TEXT NOT NULL,
                relation TEXT NOT NULL, target_id TEXT NOT NULL,
                PRIMARY KEY(run_id,kind,source_id,relation),
                FOREIGN KEY(run_id,kind,source_id) REFERENCES entities(run_id,kind,source_id),
                FOREIGN KEY(run_id,target_id) REFERENCES entities(run_id,target_id)
            );
        """)
    return connection


def build(document, group_id):
    backup.verify(document)
    report = backup.inventory(document, COMMON)
    if backup._norm(report["location"]["municipio"]) != CITY:
        raise backup.BackupError("Município do ensaio não corresponde a Itapevi.")
    group = next((row for row in report["groups"] if str(row["id"]) == str(group_id)), None)
    if not group:
        raise backup.BackupError("A turma deve pertencer a Vila das Chácaras (BR-22-2999), Itapevi.")
    run_id = str(uuid5(NAMESPACE_URL, f"sam-local-rehearsal:{VERSION}:{document['sha256']}:{group_id}"))
    namespace = UUID(run_id)
    entities, relations, issues = [], [], []
    target_ids = {}

    def issue(code, message, source=None):
        issues.append({"code": code, "message": message, "entity": source})

    def add(kind, source_id, payload, parents=None):
        source_id = str(source_id)
        if (kind, source_id) in target_ids:
            raise backup.BackupError(f"Identificador repetido no ensaio: {kind}.")
        target = str(uuid5(namespace, f"{kind}:{source_id}"))
        target_ids[(kind, source_id)] = target
        entities.append({"kind": kind, "source_id": source_id, "target_id": target, "payload": payload})
        for name, parent in (parents or {}).items():
            if parent not in target_ids:
                raise backup.BackupError("O ensaio contém vínculo sem registro de destino.")
            relations.append({"kind": kind, "source_id": source_id, "relation": name, "target_id": target_ids[parent]})
        return target

    raw_group = next(row for row in document["tables"]["sam_gem_groups"] if str(row["id"]) == str(group_id))
    add("groups", group_id, raw_group)
    calls = [row for lesson in group["classes"] for row in lesson["attendance"]]
    member_rows = defaultdict(list)
    for row in group["enrollments"] + calls:
        member = _member(row.get("source_member_id"))
        if member:
            member_rows[member].append(row)
        else:
            issue("invalid_member", "Matrícula ou chamada sem identificador de aluno válido; não recriada.", row.get("id"))
    all_students = {str(row["id"]): row for row in document["tables"]["musica_acompanhamento_aluno"]}
    states_by_member = defaultdict(list)
    profile_members = defaultdict(set)
    for row in document["tables"]["sam_student_sync_state"]:
        member = _member(row.get("source_key"))
        if member:
            states_by_member[member].append(row)
            if row.get("aluno_id"):
                profile_members[str(row["aluno_id"])].add(member)
    for table in ("sam_gem_attendance", "sam_gem_enrollments"):
        for row in document["tables"][table]:
            member = _member(row.get("source_member_id"))
            if member and row.get("aluno_id"):
                profile_members[str(row["aluno_id"])].add(member)
    history_profiles = {}
    for member, rows in sorted(member_rows.items()):
        states = states_by_member[member]
        candidate_ids = {str(row["aluno_id"]) for row in rows + states if row.get("aluno_id")}
        local_id = next(iter(candidate_ids)) if len(candidate_ids) == 1 else None
        profile = all_students.get(local_id) if local_id else None
        status = "confirmed" if profile and len(states) == 1 and str(states[0].get("aluno_id")) == local_id else "review"
        if len(candidate_ids) > 1 or (local_id and len(profile_members[local_id]) > 1):
            profile = None
            status = "ambiguous"
            issue("ambiguous_identity", "Identificadores de origem/local conflitantes; histórico individual não recriado.", member)
        elif not profile:
            issue("missing_profile", "Aluno preservado pela matrícula/chamada, sem cadastro local confirmado; histórico não inventado.", member)
        elif status != "confirmed":
            issue("identity_review", "Vínculo com cadastro local precisa ser confirmado no registro de origem.", member)
        names = {str(row.get("nome_aluno") or row.get("source_name") or "").strip() for row in rows + states}
        names.discard("")
        name = next(iter(names)) if len(names) == 1 else (profile or {}).get("nome_aluno") or f"Aluno SAM {member}"
        payload = {"source_member_id": member, "local_student_id": local_id if profile else None,
                   "name": name, "profile": profile, "source_states": states, "identity_status": status}
        add("students", member, payload)
        if profile:
            history_profiles[local_id] = member
    for enrollment in group["enrollments"]:
        member = _member(enrollment.get("source_member_id"))
        if member:
            add("enrollments", enrollment["id"], enrollment,
                {"group": ("groups", str(group_id)), "student": ("students", member)})
    for lesson in group["classes"]:
        raw = {key: value for key, value in lesson.items() if key not in {"resolved_group_id", "attendance"}}
        add("classes", lesson["id"], raw, {"group": ("groups", str(group_id))})
        for call in lesson["attendance"]:
            member = _member(call.get("source_member_id"))
            if not member:
                continue
            if not isinstance(call.get("presente"), bool):
                issue("unknown_attendance", "Chamada com presença indefinida preservada para conferência; não presumir ausência.", call["id"])
            add("attendance", call["id"], call,
                {"class": ("classes", str(lesson["id"])), "student": ("students", member)})
    history_counts = {}
    date_fields = {"msa": "data_aula", "metodo": "data_inicio", "hinario": "data", "provas": "data_prova", "escalas": "data", "atividades": "data_atividade"}
    for kind, (table, _) in SOURCE_CONFIG.items():
        count = 0
        for event in document["tables"][table]:
            member = history_profiles.get(str(event.get("aluno_id")))
            if not member:
                continue
            # O histórico pertence ao aluno. Não é relacionado à turma/aula por coincidência de datas.
            add(kind, event["id"], event, {"student": ("students", member)})
            count += 1
            if not event.get(date_fields[kind]):
                issue("history_date", "Lançamento preservado sem data; exige revisão antes de proposta de envio.", event["id"])
        history_counts[kind] = count
    counts = dict(Counter(row["kind"] for row in entities))
    for kind in ("groups", "students", "enrollments", "classes", "attendance", *SOURCE_CONFIG):
        counts.setdefault(kind, 0)
    manifest = {"location": report["location"], "group_name": group.get("turma"), "counts": counts,
                "history_counts": history_counts, "issues": issues, "sam_write_enabled": False,
                "history_scope": "Histórico individual completo dos alunos identificados; pode abranger outras turmas e localidades.",
                "created_by": None}
    return {"id": run_id, "backup_id": document["id"], "backup_sha256": document["sha256"],
            "group_id": str(group_id), "manifest": manifest, "entities": entities, "relations": relations}


def _digest(entities, relations):
    graph = {"entities": sorted(entities, key=lambda row: (row["kind"], row["source_id"])),
             "relations": sorted(relations, key=lambda row: (row["kind"], row["source_id"], row["relation"]))}
    return hashlib.sha256(_json(graph).encode("utf-8")).hexdigest()


def _graph(connection, run_id):
    entities = [{"kind": row["kind"], "source_id": row["source_id"], "target_id": row["target_id"],
                 "payload": json.loads(row["payload"])} for row in connection.execute("SELECT * FROM entities WHERE run_id=?", (run_id,))]
    relations = [{"kind": row["kind"], "source_id": row["source_id"], "relation": row["relation"], "target_id": row["target_id"]}
                 for row in connection.execute("SELECT * FROM relations WHERE run_id=?", (run_id,))]
    return entities, relations


def _verify(connection, run):
    entities, relations = _graph(connection, run["id"])
    if _digest(entities, relations) != run["content_sha256"]:
        raise backup.BackupError("O ensaio local não passou na conferência de conteúdo e vínculos.")
    if list(connection.execute("PRAGMA foreign_key_check")):
        raise backup.BackupError("O ensaio local contém vínculos inválidos.")
    expected = json.loads(run["manifest"])["counts"]
    actual = Counter(row["kind"] for row in entities)
    if any(actual[kind] != count for kind, count in expected.items()):
        raise backup.BackupError("Contagem de registros do ensaio diverge do plano.")
    return entities, relations


def create(document, group_id, created_by="Master"):
    spec = build(document, group_id)
    connection = _connect(write=True)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT * FROM runs WHERE id=?", (spec["id"],)).fetchone()
            if previous:
                _verify(connection, previous)
                return {"id": spec["id"], "reused": True, "sam_write_enabled": False}
            spec["manifest"]["created_by"] = str(created_by)
            connection.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", (
                spec["id"], spec["backup_id"], spec["backup_sha256"], spec["group_id"], COMMON, CITY,
                datetime.now(timezone.utc).isoformat(), VERSION, _json(spec["manifest"]),
                _digest(spec["entities"], spec["relations"]),
            ))
            connection.executemany("INSERT INTO entities VALUES (?,?,?,?,?)", [
                (spec["id"], row["kind"], row["source_id"], row["target_id"], _json(row["payload"])) for row in spec["entities"]])
            connection.executemany("INSERT INTO relations VALUES (?,?,?,?,?)", [
                (spec["id"], row["kind"], row["source_id"], row["relation"], row["target_id"]) for row in spec["relations"]])
            _verify(connection, connection.execute("SELECT * FROM runs WHERE id=?", (spec["id"],)).fetchone())
        return {"id": spec["id"], "reused": False, "sam_write_enabled": False}
    finally:
        connection.close()


def list_runs():
    if not _path().exists():
        return []
    connection = _connect()
    try:
        return [{"id": row["id"], "backup_id": row["backup_id"], "group_id": row["group_id"],
                 "created_at": row["created_at"], **json.loads(row["manifest"])}
                for row in connection.execute("SELECT * FROM runs ORDER BY created_at DESC")]
    finally:
        connection.close()


def read(run_id):
    try:
        run_id = str(UUID(str(run_id)))
    except (ValueError, AttributeError) as exc:
        raise backup.BackupError("Identificador de ensaio inválido.") from exc
    connection = _connect()
    try:
        run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise backup.BackupError("Ensaio local não encontrado.")
        entities, relations = _verify(connection, run)
        manifest = json.loads(run["manifest"])
        records = defaultdict(list)
        refs = defaultdict(dict)
        for edge in relations:
            refs[(edge["kind"], edge["source_id"])][edge["relation"]] = edge["target_id"]
        for entry in entities:
            records[entry["kind"]].append(entry)
        group_entry = records["groups"][0]
        group = {**group_entry["payload"], "sandbox_id": group_entry["target_id"], "enrollments": [], "classes": []}
        students, states = [], []
        for entry in records["students"]:
            payload = entry["payload"]
            student = dict(payload.get("profile") or {"id": f"sam:{entry['source_id']}", "nome_aluno": payload["name"]})
            student.update({"sandbox_id": entry["target_id"], "source_member_id": entry["source_id"],
                            "identity_status": payload["identity_status"]})
            students.append(student)
            states.extend(payload["source_states"])
        classes = {}
        for entry in records["classes"]:
            lesson = {**entry["payload"], "sandbox_id": entry["target_id"], "attendance": []}
            classes[entry["target_id"]] = lesson
            group["classes"].append(lesson)
        for entry in records["attendance"]:
            parents = refs[(entry["kind"], entry["source_id"])]
            classes[parents["class"]]["attendance"].append({**entry["payload"], "sandbox_id": entry["target_id"]})
        for entry in records["enrollments"]:
            group["enrollments"].append({**entry["payload"], "sandbox_id": entry["target_id"]})
        history = {kind: [{**entry["payload"], "sandbox_id": entry["target_id"]} for entry in records[kind]] for kind in SOURCE_CONFIG}
        group["classes"].sort(key=lambda row: row.get("data_aula") or "", reverse=True)
        counts = manifest["counts"]
        return {"id": run_id, "backup_id": run["backup_id"], "created_at": run["created_at"],
                "location": manifest["location"], "groups": [group], "students": students,
                "student_states": states, "history": history, "levels": [], "orphan_classes": [],
                "issues": manifest["issues"], "history_scope": manifest["history_scope"],
                "summary": {"groups": counts["groups"], "students": counts["students"], "enrollments": counts["enrollments"],
                            "classes": counts["classes"], "attendance": counts["attendance"],
                            "history": sum(manifest["history_counts"].values())},
                "history_counts": manifest["history_counts"], "sam_write_enabled": False,
                "verification": {"content": True, "counts": True, "relations": True},
                "id_map": [{"kind": entry["kind"], "source_id": entry["source_id"], "target_id": entry["target_id"]} for entry in entities]}
    finally:
        connection.close()
