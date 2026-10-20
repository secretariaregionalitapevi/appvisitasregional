"""Acervo local do SAM. Este módulo só lê Supabase e nunca acessa o SAM original."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
import zlib
from uuid import UUID, uuid4

import requests
from django.conf import settings
from .access_control import service_headers
from .sam_history_sync import SOURCE_CONFIG

TABLES = (
    "visitas_comuns", "sam_gem_groups", "sam_gem_enrollments", "sam_gem_classes",
    "sam_gem_attendance", "musica_acompanhamento_aluno", "sam_student_sync_state",
    "sam_level_history", "sam_audit_events", *(table for table, _ in SOURCE_CONFIG.values()),
)
PAGE_SIZE = 1000
SCHEMA_VERSION = 1


class BackupError(Exception):
    pass


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).upper().split())


def common_key(value):
    text = _norm(value)
    match = re.match(r"^(BR-\d+(?:-\d+)+)(?:\s|$)", text)
    return match.group(1) if match else text


def _read_table(table, client=None):
    # Ordens estáveis e contagem exata evitam aceitar o limite padrão do PostgREST
    # como se fosse a totalidade da tabela. Não existe transação entre tabelas.
    rows, expected, offset = [], None, 0
    order = "comum.asc,cidade.asc" if table == "visitas_comuns" else "id.asc"
    while True:
        response = (client or requests).get(
            f"{settings.SUPABASE_URL}/rest/v1/{table}",
            headers=service_headers("count=exact"),
            params={"select": "*", "order": order, "offset": offset, "limit": PAGE_SIZE},
            timeout=(5, 60),
        )
        if not response.ok:
            raise BackupError(f"Não foi possível ler {table} (HTTP {response.status_code}). Nenhuma cópia foi criada.")
        batch = response.json()
        if not isinstance(batch, list):
            raise BackupError(f"Resposta inválida em {table}.")
        total = response.headers.get("Content-Range", "").rsplit("/", 1)[-1]
        if not total.isdigit():
            raise BackupError(f"A contagem exata de {table} não foi fornecida; captura recusada.")
        if expected is None:
            expected = int(total)
        elif expected != int(total):
            raise BackupError(f"{table} mudou durante a leitura. Repita a captura em um intervalo sem sincronização.")
        rows.extend(batch)
        offset += len(batch)
        if offset >= expected:
            if offset != expected:
                raise BackupError(f"Contagem inconsistente em {table}.")
            break
        if not batch:
            raise BackupError(f"Leitura incompleta de {table}.")
    if table != "visitas_comuns" and len({str(row.get("id")) for row in rows}) != len(rows):
        raise BackupError(f"Registros repetidos durante a leitura de {table}; captura recusada.")
    return rows


def capture(progress=None):
    def read(table):
        with requests.Session() as client:
            rows = _read_table(table, client)
        if progress:
            progress(table, len(rows))
        return rows
    started = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(read, TABLES))
    return {
        "schema_version": SCHEMA_VERSION,
        "id": str(uuid4()), "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "source": "espelho local Supabase; sem acesso ao SAM original",
        "consistent_transaction": False,
        "attachments": "Somente referências e URLs; arquivos binários não foram capturados.",
        "tables": dict(zip(TABLES, results)),
    }


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def seal(document):
    document = {key: value for key, value in document.items() if key != "sha256"}
    return {**document, "sha256": hashlib.sha256(_encoded(document)).hexdigest()}


def verify(document):
    if not isinstance(document, dict):
        raise BackupError("Estrutura de backup inválida.")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise BackupError("Versão de backup não suportada.")
    if document.get("sha256") != seal(document)["sha256"]:
        raise BackupError("A assinatura de integridade não confere; cópia recusada.")
    if set(document.get("tables", {})) != set(TABLES):
        raise BackupError("A cópia não contém todas as tabelas previstas.")
    if any(not isinstance(rows, list) for rows in document["tables"].values()):
        raise BackupError("Estrutura de tabelas inválida.")
    return document


def archive_dir():
    directory = Path(getattr(settings, "SAM_BACKUP_DIR", None) or (Path(settings.BASE_DIR) / ".backups" / "sam"))
    return directory


def _archive_path(backup_id):
    try:
        backup_id = str(UUID(str(backup_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise BackupError("Identificador de backup inválido.") from exc
    return archive_dir() / f"{backup_id}.json.gz"


def save(document):
    if getattr(settings, "IS_PRODUCTION", False) and not getattr(settings, "SAM_BACKUP_DIR", None):
        raise BackupError("Configure SAM_BACKUP_DIR em armazenamento persistente antes de criar cópias neste ambiente.")
    document = seal(document)
    verify(document)
    directory = archive_dir()
    directory.mkdir(parents=True, exist_ok=True)
    destination = _archive_path(document["id"])
    temporary = directory / f".{uuid4()}.tmp"
    try:
        with temporary.open("xb") as output:
            output.write(gzip.compress(_encoded(document), mtime=0))
            output.flush()
            os.fsync(output.fileno())
        # Hard link publica somente um arquivo completo e nunca sobrescreve uma versão.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    try:
        _write_index(document, destination)
    except OSError:
        pass
    return document


def load(backup_id):
    try:
        document = verify(json.loads(gzip.decompress(_archive_path(backup_id).read_bytes())))
        if document.get("id") != str(UUID(str(backup_id))):
            raise BackupError("O identificador interno da cópia não confere.")
        return document
    except (OSError, ValueError, EOFError, zlib.error) as exc:
        raise BackupError("Cópia inexistente, inacessível ou inválida.") from exc


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_index(document, path):
    # Índice derivado: acelera a listagem sem descomprimir todas as versões.
    # O arquivo de dados permanece intacto e downloads sempre validam o conteúdo.
    summary = {"id": document["id"], "finished_at": document["finished_at"], "valid": True,
               "counts": {table: len(rows) for table, rows in document["tables"].items()},
               "sha256": document["sha256"], "archive_sha256": _file_digest(path)}
    index = {**summary, "index_sha256": hashlib.sha256(_encoded(summary)).hexdigest()}
    temporary = path.parent / f".{uuid4()}.tmp"
    try:
        temporary.write_bytes(_encoded(index))
        os.replace(temporary, path.with_suffix(".index.json"))
    finally:
        temporary.unlink(missing_ok=True)
    return summary


def _archive_summary(path):
    backup_id = path.name.removesuffix(".json.gz")
    index_path = path.with_suffix(".index.json")
    try:
        index = json.loads(index_path.read_bytes())
        signature = index.pop("index_sha256")
        if (index["id"] == backup_id and signature == hashlib.sha256(_encoded(index)).hexdigest()
                and index["archive_sha256"] == _file_digest(path)
                and set(index["counts"]) == set(TABLES)):
            return index
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        pass
    document = load(backup_id)
    try:
        return _write_index(document, path)
    except OSError:
        # Sem permissão para criar o cache, a cópia continua consultável.
        return {"id": backup_id, "finished_at": document["finished_at"], "valid": True,
                "counts": {table: len(rows) for table, rows in document["tables"].items()},
                "sha256": document["sha256"]}


def list_archives():
    result = []
    for path in archive_dir().glob("*.json.gz"):
        backup_id = path.name.removesuffix(".json.gz")
        try:
            result.append(_archive_summary(path))
        except BackupError:
            result.append({"id": backup_id, "valid": False, "finished_at": None})
    return sorted(result, key=lambda row: row.get("finished_at") or "", reverse=True)


def locations(tables, include_pending=False):
    catalog = tables["visitas_comuns"]
    known, canonical_cities = {}, {}
    aliases = defaultdict(set)
    # Normaliza caixa, acentuação e espaços para a identidade do município.
    # Preserva a grafia do catálogo, em maiúsculas, para apresentação.
    for row in catalog:
        city = str(row.get("cidade") or row.get("municipio") or "").strip()
        if city:
            canonical_cities.setdefault(_norm(city), " ".join(city.upper().split()))

    def city_label(value):
        raw = " ".join(str(value or "").strip().split())
        if not raw or _norm(raw) == "MUNICIPIO NAO IDENTIFICADO":
            return None
        return canonical_cities.setdefault(_norm(raw), raw.upper())

    for row in catalog:
        label = str(row.get("comum") or "").strip()
        if not label:
            continue
        key = common_key(label)
        known[key] = {"key": key, "label": label,
                      "municipio": city_label(row.get("cidade") or row.get("municipio"))}
        aliases[_norm(re.sub(r"^BR-\d+(?:-\d+)+\s*-\s*", "", label))].add(key)

    def resolve(value):
        key = common_key(value)
        if key in known:
            return key
        candidates = aliases.get(_norm(value), set())
        return next(iter(candidates)) if len(candidates) == 1 else key

    source_cities, local_cities = defaultdict(set), defaultdict(set)
    for table, field in (("sam_gem_groups", "congregacao"), ("sam_gem_classes", "congregacao"),
                         ("musica_acompanhamento_aluno", "comum_congregacao"),
                         ("sam_student_sync_state", "source_common"), ("sam_audit_events", "congregation_snapshot")):
        for row in tables[table]:
            value = row.get(field)
            if not value:
                continue
            key = resolve(value)
            known.setdefault(key, {"key": key, "label": value, "municipio": None})
            local_city = city_label(row.get("municipio") or row.get("cidade"))
            if local_city:
                local_cities[key].add(local_city)
            if table == "sam_student_sync_state":
                payload = row.get("source_payload") or {}
                source_city = city_label(payload.get("city")) if isinstance(payload, dict) else None
                if source_city:
                    source_cities[key].add(source_city)

    for key, location in known.items():
        if location["municipio"]:
            continue
        # O cadastro original fornece município da comum, sem inferir pelo nome
        # nem pelo município de alunos que apenas frequentam outra localidade.
        cities = source_cities[key] or local_cities[key]
        if len(cities) == 1:
            location["municipio"] = next(iter(cities))

    ordered = sorted(known.values(), key=lambda row: (_norm(row["municipio"]), _norm(row["label"])))
    visible = [row for row in ordered if row["municipio"]]
    pending = [row for row in ordered if not row["municipio"]]
    # Nunca oferece uma classificação fictícia no seletor; pendências reais são
    # expostas separadamente e os dados originais continuam no arquivo completo.
    if include_pending:
        return visible, resolve, pending
    return visible, resolve


def inventory(document, selected):
    tables = document["tables"]
    options, resolve = locations(tables)
    location = next((row for row in options if row["key"] == selected), None)
    if not location:
        raise BackupError("Selecione uma comum existente no acervo.")
    issues = []
    def issue(code, message, entity=None):
        issues.append({"code": code, "message": message, "entity": entity})
    groups = [dict(row) for row in tables["sam_gem_groups"] if resolve(row.get("congregacao")) == selected]
    group_ids = {str(row["id"]) for row in groups}
    group_sources = {str(row.get("source_id")): str(row["id"]) for row in groups if row.get("source_id") is not None}
    classes = [dict(row) for row in tables["sam_gem_classes"] if str(row.get("turma_id")) in group_ids
               or str(row.get("turma_source_id")) in group_sources or resolve(row.get("congregacao")) == selected]
    for row in classes:
        parent = str(row.get("turma_id"))
        if parent not in group_ids:
            parent = group_sources.get(str(row.get("turma_source_id")))
        row["resolved_group_id"] = parent
        if not parent:
            issue("orphan_class", "Aula sem turma preservada nesta comum.", row.get("id"))
    class_ids = {str(row["id"]) for row in classes}
    attendance = [row for row in tables["sam_gem_attendance"] if str(row.get("aula_id")) in class_ids]
    enrollments = [row for row in tables["sam_gem_enrollments"] if str(row.get("turma_id")) in group_ids]
    linked_ids = {str(row["aluno_id"]) for row in attendance + enrollments if row.get("aluno_id")}
    members = {str(row["source_member_id"]) for row in attendance + enrollments if row.get("source_member_id") is not None}
    states = [row for row in tables["sam_student_sync_state"] if str(row.get("source_key")) in members
              or str(row.get("aluno_id")) in linked_ids or resolve(row.get("source_common")) == selected]
    linked_ids.update(str(row["aluno_id"]) for row in states if row.get("aluno_id"))
    students = [row for row in tables["musica_acompanhamento_aluno"] if str(row["id"]) in linked_ids
                or resolve(row.get("comum_congregacao")) == selected]
    student_ids = {str(row["id"]) for row in students}
    for row in attendance + enrollments:
        if not row.get("aluno_id") or str(row["aluno_id"]) not in student_ids:
            issue("unlinked_student", "Chamada ou matrícula sem cadastro local de aluno confirmado.", row.get("id"))
    identities = defaultdict(set)
    for row in states:
        if row.get("aluno_id"):
            identities[str(row.get("aluno_id"))].add(str(row.get("source_key")))
        if row.get("sync_status") in {"ambiguous", "unmatched", "failed"}:
            issue("sync_pending", "Identificação ou sincronização do aluno exige revisão.", row.get("id"))
    for row in attendance + enrollments:
        if row.get("aluno_id") and row.get("source_member_id") is not None:
            identities[str(row["aluno_id"])].add(str(row["source_member_id"]))
    state_links = {(str(row.get("aluno_id")), str(row.get("source_key"))) for row in states if row.get("aluno_id")}
    for student in students:
        ids = identities[str(student["id"])]
        if len(ids) != 1:
            issue("source_identity", "Aluno sem identificador único no acervo SAM.", student["id"])
        elif (str(student["id"]), next(iter(ids))) not in state_links:
            issue("identity_evidence", "Identificador obtido apenas de chamada ou matrícula; conferir o cadastro de origem.", student["id"])
    calls_by_class = defaultdict(list)
    for row in attendance:
        calls_by_class[str(row["aula_id"])].append(row)
        if not isinstance(row.get("presente"), bool):
            issue("attendance_value", "Presença não informada; não presumir ausência.", row.get("id"))
    for row in classes:
        if not calls_by_class[str(row["id"])]:
            issue("empty_attendance", "Aula sem chamada capturada.", row["id"])
        if not row.get("data_aula"):
            issue("class_date", "Aula sem data comprovada.", row["id"])
    enrolled_by_group = defaultdict(list)
    for row in enrollments:
        enrolled_by_group[str(row["turma_id"])].append(row)
    classes_by_group = defaultdict(list)
    orphan_classes = []
    for row in classes:
        row["attendance"] = calls_by_class[str(row["id"])]
        if row["resolved_group_id"]:
            classes_by_group[row["resolved_group_id"]].append(row)
        else:
            orphan_classes.append(row)
    for group in groups:
        end = group.get("data_termino")
        try:
            period_ended = bool(end and datetime.fromisoformat(str(end)).date() < datetime.fromisoformat(document["finished_at"]).date())
        except (ValueError, TypeError):
            period_ended = False
        group["archive_period_ended"] = period_ended
        group["archive_status"] = "Período encerrado" if period_ended else "Finalizada" if group.get("ativo") is False else "Ativa" if group.get("ativo") is True else "Situação não confirmada"
        group["enrollments"] = enrolled_by_group[str(group["id"])]
        group["classes"] = sorted(classes_by_group[str(group["id"])], key=lambda row: row.get("data_aula") or "", reverse=True)
        captured_members = {str(row.get("source_member_id")) for row in group["enrollments"]}
        if group.get("matriculados") is not None and int(group["matriculados"]) != len(captured_members):
            issue("enrollment_count", "Quantidade informada na turma difere das matrículas capturadas; datas de referência podem diferir.", group["id"])
        if not group.get("source_id") or not group.get("curso") or not group.get("turma"):
            issue("group_fields", "Turma com identificação incompleta.", group["id"])
    history = {}
    for name, (table, _) in SOURCE_CONFIG.items():
        history[name] = [row for row in tables[table] if str(row.get("aluno_id")) in student_ids
                         or resolve(row.get("comum_congregacao")) == selected]
        for row in history[name]:
            if str(row.get("aluno_id")) not in student_ids:
                issue("orphan_history", "Lançamento sem cadastro de aluno preservado neste acervo.", row.get("id"))
    levels = [row for row in tables["sam_level_history"] if str(row.get("aluno_id")) in student_ids]
    target_sources = {"turma": set(group_sources), "group": set(group_sources),
                      "aula": {str(row.get("source_id")) for row in classes},
                      "class": {str(row.get("source_id")) for row in classes},
                      "aluno": members, "student": members}
    audits = [row for row in tables["sam_audit_events"] if resolve(row.get("congregation_snapshot")) == selected
              or (row.get("target_type") in {"turma", "group", "aula", "class", "aluno", "student"}
                  and str(row.get("target_source_id")) in target_sources.get(row.get("target_type"), set()))]
    dates = sorted(row["data_aula"] for row in classes if row.get("data_aula"))
    limits = [
        "A completude em relação ao SAM original ainda não foi verificada.",
        "Matrículas capturadas a partir de chamadas podem não incluir alunos que nunca tiveram chamada registrada.",
        "Históricos individuais não são atribuídos a uma turma sem vínculo explícito.",
        "Lançamentos locais e importados devem ter sua origem revisada antes de qualquer proposta de recuperação.",
        "URLs de documentos foram preservadas; os arquivos anexos ainda não integram esta cópia.",
        "Leitura entre tabelas não é transacional; uma sincronização simultânea pode gerar divergências.",
    ]
    plan = {
        "status": "blocked", "sam_write_enabled": False,
        "reason": "Nenhum registro está liberado para envio. O acervo preservado não comprova exclusão no SAM; a comparação atual com o sistema original ainda não foi realizada.",
        "steps": [
            {"order": 1, "entity": "Turmas", "count": len(groups)},
            {"order": 2, "entity": "Identificação dos alunos e matrículas", "count": len(enrollments)},
            {"order": 3, "entity": "Aulas", "count": len(classes)},
            {"order": 4, "entity": "Chamadas", "count": len(attendance)},
            {"order": 5, "entity": "Lançamentos individuais", "count": sum(map(len, history.values()))},
        ],
        "required_checks": ["Validar alunos por identificadores, sem associação automática por nome",
                            "Consultar o SAM atual com leitura completa, incluindo turmas finalizadas, todas as páginas e todas as categorias do histórico dos alunos",
                            "Classificar cada registro como existente, ausência confirmada ou pendente; somente ausência confirmada pode compor uma proposta de envio",
                            "Comparar identificadores originais e conteúdo; IDs diferentes com conteúdo equivalente ou divergências exigem revisão, nunca criação automática",
                            "Verificar MSA, método, hinário, provas, escalas e progresso por aluno, mesmo se a turma estiver ausente; não reenviar histórico por ausência da turma",
                            "Preservar o estado finalizado e as datas das turmas; finalização não significa exclusão",
                            "Bloquear ausência quando a consulta estiver incompleta, desatualizada, sem identidade inequívoca ou com vínculos pendentes",
                            "Antes de cada futura criação, consultar novamente o destino e registrar o ID resultante; após falha ou timeout, conferir o SAM antes de qualquer tentativa",
                            "Exigir idempotência ou unicidade no destino e controle de concorrência; sem essa garantia técnica, manter o envio bloqueado",
                            "Validar operações suportadas pelo SAM em ambiente de teste",
                            "Mapear IDs antigos para novos e testar retomada",
                            "Conferir os resultados do ensaio antes de qualquer autorização"],
    }
    return {
        "location": location, "captured_at": document["finished_at"],
        "backup_id": document["id"] if document.get("sha256") else None,
        "summary": {"groups": len(groups), "active_groups": sum(g.get("ativo") is True and not g["archive_period_ended"] for g in groups),
                    "finished_groups": sum(g.get("ativo") is False or g["archive_period_ended"] for g in groups),
                    "unconfirmed_groups": sum(g.get("ativo") is not True and g.get("ativo") is not False and not g["archive_period_ended"] for g in groups), "students": len(students), "enrollments": len(enrollments),
                    "classes": len(classes), "attendance": len(attendance), "history": sum(map(len, history.values())),
                    "issues": len(issues), "first_class": dates[0] if dates else None, "last_class": dates[-1] if dates else None},
        "groups": groups, "orphan_classes": orphan_classes, "students": students,
        "student_states": states, "history": history, "levels": levels, "audit": audits,
        "issues": issues, "limitations": limits, "plan": plan,
        "global_diagnostics": global_diagnostics(tables),
    }


def global_diagnostics(tables):
    """Não descarta silenciosamente registros cuja localidade não pode ser determinada."""
    groups = {str(row["id"]) for row in tables["sam_gem_groups"]}
    classes = {str(row["id"]) for row in tables["sam_gem_classes"]}
    students = {str(row["id"]) for row in tables["musica_acompanhamento_aluno"]}
    return {
        "Chamadas sem aula preservada": sum(str(row.get("aula_id")) not in classes for row in tables["sam_gem_attendance"]),
        "Matrículas sem turma preservada": sum(str(row.get("turma_id")) not in groups for row in tables["sam_gem_enrollments"]),
        "Lançamentos sem cadastro de aluno": sum(str(row.get("aluno_id")) not in students for table, _ in SOURCE_CONFIG.values() for row in tables[table]),
        "Mudanças de nível sem cadastro de aluno": sum(str(row.get("aluno_id")) not in students for row in tables["sam_level_history"]),
    }
