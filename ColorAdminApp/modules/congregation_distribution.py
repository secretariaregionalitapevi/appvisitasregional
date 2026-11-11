"""Distribuição por comum, independente da residência e do cargo de origem."""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

TABLE = "administrative_congregation_distribution"
ROLES = {"anciao": "Ancião", "regional": "Encarregado Regional", "examinadora": "Examinadora de Organista", "secretario": "Secretário da Música"}
ADMINISTRATIONS = {
    "COTIA": "cotia_caucaia_vgp", "CAUCAIA": "cotia_caucaia_vgp",
    "CAUCAIA DO ALTO": "cotia_caucaia_vgp", "VGP": "cotia_caucaia_vgp",
    "VARGEM GRANDE PAULISTA": "cotia_caucaia_vgp",
    "JANDIRA": "jandira", "ITAPEVI": "itapevi",
    "SANTANA": "santana_pirapora", "SANTANA DE PARNAIBA": "santana_pirapora",
    "PIRAPORA": "santana_pirapora", "PIRAPORA DO BOM JESUS": "santana_pirapora",
}


def administration(city):
    normalized = " ".join("".join(c for c in unicodedata.normalize("NFD", str(city or "").upper())
                                   if not unicodedata.combining(c)).split())
    return ADMINISTRATIONS.get(normalized, "")


def scoped_directory(persons, catalog):
    groups = {common_code(c["comum"]): administration(c.get("cidade") or c.get("municipio")) for c in catalog}
    return {identity: {**person, "administration_ids": sorted({groups[c] for c in
            (person.get("residence_codes") or person.get("origin_codes") or []) if groups.get(c)})}
            for identity, person in persons.items()}


class ResidenceConflict(ValueError):
    pass


def common_code(value):
    match = re.search(r"BR-\d{2}-\d{4}", str(value or ""))
    return match[0] if match else ""


def person_display_name(value):
    """Cargo é exibido no campo próprio, não como parte do nome da pessoa."""
    return " ".join(re.sub(r"\(\s*organista\s*\)", "", str(value or ""), flags=re.IGNORECASE).split())


@lru_cache(maxsize=1)
def seed():
    path = Path(__file__).resolve().parents[1] / "data" / "congregation_assignments.json"
    return json.loads(path.read_text(encoding="utf-8"))


def corrected_catalog(catalog):
    return [{**row, "comum": corrected_common(row.get("comum"))} for row in catalog]


def corrected_common(value):
    def normalized(text):
        return " ".join(unicodedata.normalize("NFC", str(text or "")).upper().split())
    for correction in seed().get("catalog_corrections", []):
        if normalized(value) == normalized(correction["before"]):
            return correction["after"]
    return value


def load_overrides(read):
    import requests
    try:
        return read(TABLE, {"select": "*", "order": "congregation_code.asc", "limit": "1000"}), True
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return [], False
        raise


def directory(people, overrides=()):
    result = {}
    for person in people:
        identity = f"{person['source']}:{person['source_id']}"
        raw_role = "".join(c for c in unicodedata.normalize("NFD", person["ministerio"].upper()) if not unicodedata.combining(c))
        roles = ["anciao"] if raw_role == "ANCIAO" else ["regional"] if "ENCARREGADO REGIONAL" in raw_role else ["examinadora"] if "EXAMINADORA" in raw_role else ["secretario"] if "SECRET" in raw_role and "MUSICA" in raw_role else []
        result[identity] = {
            "person_id": identity, "nome": person_display_name(person["nome"]),
            "residence_codes": [common_code(person["comum"])],
            "origin_codes": [common_code(person["comum"])],
            "ministerio": person["ministerio"],
            "status": person.get("status"),
            "roles": roles,
        }
    # A residência confirmada da relação prevalece sobre uma antiga lotação.
    for assignment in seed()["assignments"]:
        identity = assignment["person_id"]
        result[identity] = {**result.get(identity, {}), "person_id": identity,
                            "nome": result.get(identity, {}).get("nome") or person_display_name(assignment["nome"]), "residence_codes": assignment["residence_codes"],
                            "roles": sorted(set(result.get(identity, {}).get("roles", []) + [assignment["role"]]))}
    for override in sorted(overrides, key=lambda row: str(row.get("updated_at") or "")):
        for assignment in override.get("assignments") or []:
            identity = assignment["person_id"]
            if identity in result:
                result[identity] = {**result[identity], "residence_codes": assignment.get("residence_codes", [])}
    return result


def annotate(item, target):
    residences = item.get("residence_codes") or []
    return {**item, "relationship": "residente" if target in residences else "assistencia" if residences else "a_confirmar"}


def apply(rows, people, overrides=(), editable=True):
    by_common = {}
    for item in seed()["assignments"]:
        by_common.setdefault(item["congregation_code"], []).append(item)
    stored = {row["congregation_code"]: row for row in overrides}
    persons = directory(people, overrides)
    pending = seed().get("pending", [])
    for row in rows:
        code = row["codigo"]
        override = stored.get(code)
        assignments = (override.get("assignments") or []) if override else by_common.get(code, [])
        row["assignments"] = [annotate({**a,
                                       "nome": persons.get(a["person_id"], {}).get("nome") or person_display_name(a["nome"]),
                                       "residence_codes": persons.get(a["person_id"], a).get("residence_codes", [])}, code) for a in assignments]
        row["assignment_revision"] = override["revision"] if override else 0
        row["assignment_editable"] = editable
        row["assignment_pending"] = [p for p in pending if p.get("congregation_code") == code]
        row["missing_assignment_roles"] = [] if any(a["role"] == "examinadora" for a in assignments) else ["examinadora"]
        if code not in by_common and override is None:
            continue
        # Manter os outros ministérios/cargos. Estes quatro são geridos pela
        # distribuição oficial, não apenas pela lotação da pessoa.
        native = [p for p in row["servos"] if not (
            p.get("categoria") in {"encarregados_regionais", "examinadoras", "secretarios_musica"}
            or str(p.get("ministerio") or "").upper() in {"ANCIÃO", "ANCIAO"}
        )]
        for person in native:
            person["person_key"] = f"{person['source']}:{person['source_id']}"
            person["relationship"] = "residente"
        assigned = []
        for item in row["assignments"]:
            person = persons.get(item["person_id"], {})
            role = item.get("role_label") or ROLES[item["role"]]
            if item["role"] == "secretario" and str(person.get("ministerio") or "").upper().startswith("SECRETÁRIA"):
                role = "Secretária da Música"
            assigned.append({
                "id": f"distribution:{item['person_id']}:{item['role']}",
                "person_key": item["person_id"], "source_id": item["person_id"].split(":", 1)[-1],
                "source": item["person_id"].split(":", 1)[0], "nome": item["nome"],
                "ministerio": role, "comum": row["nome"], "municipio": row["municipio"],
                "status": person.get("status") or "Ativo", "relationship": item["relationship"],
                "residence_codes": item.get("residence_codes", []),
                "categoria": {"anciao": "ministerio", "regional": "encarregados_regionais", "examinadora": "examinadoras", "secretario": "secretarios_musica"}[item["role"]],
            })
        row["servos"] = assigned + native
        row["quantidade_servos"] = len({p["person_key"] for p in row["servos"]})
    return list(persons.values())


def validate_assignments(items, persons, catalog, target_code=None):
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("A distribuição deve ser uma lista com até 100 vínculos.")
    codes = {common_code(c["comum"]) for c in catalog}
    groups = {common_code(c["comum"]): administration(c.get("cidade") or c.get("municipio")) for c in catalog}
    target_group = groups.get(target_code) if target_code else None
    if target_code and not target_group:
        raise ValueError("Não foi possível identificar a administração da comum.")
    scoped = scoped_directory(persons, catalog) if target_code else persons
    result, seen, residence_by_person = [], set(), {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Vínculo inválido.")
        role, identity = item.get("role"), item.get("person_id")
        if not isinstance(role, str) or not isinstance(identity, str) or role not in ROLES or identity not in persons:
            raise ValueError("Selecione uma pessoa cadastrada e um cargo válido.")
        if role not in persons[identity].get("roles", []):
            raise ValueError("A pessoa selecionada não está cadastrada para este ministério ou cargo.")
        if target_code and target_group not in scoped[identity]["administration_ids"]:
            raise ValueError("A pessoa selecionada pertence a outra administração.")
        if (role, identity) in seen:
            raise ValueError("A mesma pessoa não pode aparecer duas vezes no mesmo cargo.")
        seen.add((role, identity))
        residences = item.get("residence_codes", persons[identity].get("residence_codes", []))
        if not isinstance(residences, list) or any(not isinstance(c, str) or c not in codes for c in residences):
            raise ValueError("Selecione comuns de residência válidas.")
        normalized_residences = sorted(set(residences))
        if target_code and any(groups.get(c) != target_group for c in normalized_residences):
            raise ValueError("Selecione residências dentro da administração desta comum.")
        expected = item.get("expected_residence_codes")
        current_residences = sorted(set(persons[identity].get("residence_codes", [])))
        if expected is not None and (not isinstance(expected, list) or any(not isinstance(c, str) for c in expected)):
            raise ValueError("Versão das residências inválida.")
        if expected is not None and sorted(set(expected)) != current_residences:
            raise ResidenceConflict("As residências desta pessoa foram alteradas em outra comum. Atualize antes de salvar.")
        if identity in residence_by_person and residence_by_person[identity] != normalized_residences:
            raise ValueError("Informe as mesmas residências para todos os cargos da mesma pessoa.")
        residence_by_person[identity] = normalized_residences
        label = ROLES[role]
        if role == "secretario":
            known_labels = [a.get("role_label") for a in seed()["assignments"] if a["person_id"] == identity and a["role"] == role]
            if "Secretária da Música" in known_labels or str(persons[identity].get("ministerio") or "").upper().startswith("SECRETÁRIA"):
                label = "Secretária da Música"
        result.append({"role": role, "role_label": label, "person_id": identity, "nome": persons[identity]["nome"],
                       "residence_codes": normalized_residences, "source_document": "Alteração administrativa", "source_row": None})
    return result
