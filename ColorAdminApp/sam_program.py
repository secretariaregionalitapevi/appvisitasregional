"""Avaliação documental do Programa Mínimo de músicos e organistas (Circular 158/2023)."""
import re
import unicodedata


def norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).upper().split())


LEVELS = {
    "rjm": {"label": "Reunião de Jovens e Menores", "msa_phase": 12, "hymns": (431, 480)},
    "culto": {"label": "Cultos Oficiais", "msa_phase": 16, "hymns": (1, 480)},
    "oficializacao": {"label": "Oficialização", "msa_phase": 16, "hymns": (1, 480), "revision": True},
}


METHOD_PROGRAM = {
    "VIOLINO": {
        "rjm": "N. Laoureux vol. 1 até pág. 35; ou Schimoll até pág. 46 (lição 113) + H. Sitt vol. 1 até lição 6; ou Método Facilitado Britten até pág. 40.",
        "culto": "N. Laoureux vol. 1 completo + vol. 3 até pág. 15; ou Schimoll até pág. 67 (lição 162) + H. Sitt vol. 1 até lição 14; ou Método Facilitado Britten até pág. 55.",
        "oficializacao": "N. Laoureux vol. 1 completo + vol. 3 págs. 24 e 44 a 53; ou Schimoll completo + H. Sitt Op. 32 vol. 1 completo; ou Método Facilitado Britten completo.",
    },
    "VIOLA": {
        "rjm": "Beginning Strings até lição VI + Berta Volmer vol. 1 até pág. 31; ou Método Facilitado Britten até pág. 40.",
        "culto": "Berta Volmer vol. 1 até pág. 62 + A Tune a Day vol. 3 até pág. 16; ou Método Facilitado Britten até pág. 55.",
        "oficializacao": "Berta Volmer vol. 1 completo + A Tune a Day vol. 3 completo; ou Método Facilitado Britten completo.",
    },
    "VIOLONCELO": {
        "rjm": "Beginning Strings até lição VI + Dotzauer vol. 1 até pág. 34 (lição 80); ou Método Facilitado Britten até pág. 40.",
        "culto": "Dotzauer vol. 1 completo + vol. 2 até pág. 3 (lição 111); ou Método Facilitado Britten até pág. 52.",
        "oficializacao": "Dotzauer vol. 1 completo + vol. 2 até pág. 19 (lição 154); ou Método Facilitado Britten completo.",
    },
    "FLAUTA": {
        "rjm": "Rubank Elementary completo; ou Parès até lição 41; ou Galli até pág. 41; ou Método Prático Almeida Dias até fase 13.",
        "culto": "Rubank Intermediate até pág. 29; ou Parès até lição 62; ou Galli completo; ou Método Prático Almeida Dias até fase 25.",
        "oficializacao": "Rubank Intermediate completo; ou Parès até lição 62; ou Galli completo; ou Método Prático Almeida Dias até fase 25.",
    },
    "CLARINETE": {
        "rjm": "Giampieri até pág. 28; ou Domingos Pecci até pág. 29; ou Galper book 1 até exercício 110.",
        "culto": "Giampieri até pág. 41; ou Domingos Pecci até pág. 36.",
        "oficializacao": "Giampieri até pág. 63; ou Domingos Pecci completo; ou Galper book 1 completo + book 2 até pág. 29.",
    },
    "SAXOFONE": {
        "rjm": "Giampieri até pág. 21; ou Amadeu Russo até pág. 25; ou Método Prático Almeida Dias até fase 13.",
        "culto": "Giampieri até pág. 30; ou Amadeu Russo até pág. 40; ou Método Prático Almeida Dias até fase 25.",
        "oficializacao": "Giampieri até pág. 50; ou Amadeu Russo até pág. 55; ou Método Prático Almeida Dias completo.",
    },
    "TROMPETE": {
        "rjm": "Rubank Elementary para Cornet/Trumpet completo.",
        "culto": "Robert Getchel Second Book exercícios 65 a 94; ou Amadeu Russo até pág. 30; ou Método Prático Almeida Dias até fase 25.",
        "oficializacao": "Robert Getchel Second Book completo; ou Amadeu Russo até pág. 41; ou Método Prático Almeida Dias completo.",
    },
    "TROMPA": {
        "rjm": "Rubank Elementary completo + Método Prático para Trompa até lição 73.",
        "culto": "Rubank Elementary e Intermediate completos + Método Prático para Trompa até lição 105.",
        "oficializacao": "Rubank Elementary e Intermediate completos + Método Prático para Trompa completo.",
    },
    "TROMBONE": {
        "rjm": "Rubank Elementary até pág. 24; ou Método Prático Almeida Dias até fase 13.",
        "culto": "Rubank Elementary até pág. 37; ou Método Prático Almeida Dias até fase 25.",
        "oficializacao": "Rubank Elementary até pág. 48; ou Método Prático Almeida Dias completo.",
    },
    "EUFONIO": {}, "TUBA": {},
}
METHOD_PROGRAM["EUFONIO"] = METHOD_PROGRAM["TROMBONE"]
METHOD_PROGRAM["TUBA"] = METHOD_PROGRAM["TROMBONE"]


def target_for_level(level):
    value = norm(level)
    if "OFICIALIZAD" in value:
        return "concluido"
    if "CULTO OFICIAL" in value:
        return "oficializacao"
    if "RJM" in value or "MEIA HORA" in value:
        return "culto"
    return "rjm"


def instrument_group(instrument, ministry=""):
    value = norm(instrument)
    if "ORGANISTA" in norm(ministry) or value in {"ORGAO", "ORGANISTA"}:
        return "ORGAO"
    for key in METHOD_PROGRAM:
        if key in value:
            return key
    if "SAX" in value:
        return "SAXOFONE"
    if "EUPHON" in value:
        return "EUFONIO"
    return value or "NAO INFORMADO"


def _numbers(value):
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(value or ""))]


def _maximum(rows, fields):
    values = [number for row in rows or [] for field in fields for number in _numbers(row.get(field))]
    return max(values) if values else 0


def _documented_hymns(rows):
    result = set()
    for row in rows or []:
        numbers = [int(x) for x in re.findall(r"\d+", str(row.get("hino") or ""))]
        if len(numbers) >= 2 and 0 < numbers[1] - numbers[0] <= 480:
            result.update(range(numbers[0], numbers[1] + 1))
        else:
            result.update(number for number in numbers if 1 <= number <= 480)
    return result


def _method_threshold_met(rows, group, target):
    """Confere alternativas por página/lição; conclusão explícita atende metas sem número."""
    rules = {
        "VIOLINO": {"rjm": (("LAOUREUX", "pagina", 35), ("SCHIMOLL", "pagina", 46), ("BRITTEN", "pagina", 40)), "culto": (("SCHIMOLL", "pagina", 67), ("BRITTEN", "pagina", 55))},
        "VIOLA": {"rjm": (("VOLMER", "pagina", 31), ("BRITTEN", "pagina", 40)), "culto": (("VOLMER", "pagina", 62), ("BRITTEN", "pagina", 55))},
        "VIOLONCELO": {"rjm": (("DOTZAUER", "pagina", 34), ("BRITTEN", "pagina", 40)), "culto": (("DOTZAUER", "licao", 111), ("BRITTEN", "pagina", 52)), "oficializacao": (("DOTZAUER", "licao", 154),)},
        "FLAUTA": {"rjm": (("PARES", "licao", 41), ("GALLI", "pagina", 41), ("ALMEIDA DIAS", "licao", 13)), "culto": (("RUBANK", "pagina", 29), ("PARES", "licao", 62), ("ALMEIDA DIAS", "licao", 25))},
        "CLARINETE": {"rjm": (("GIAMPIERI", "pagina", 28), ("PECCI", "pagina", 29), ("GALPER", "licao", 110)), "culto": (("GIAMPIERI", "pagina", 41), ("PECCI", "pagina", 36)), "oficializacao": (("GIAMPIERI", "pagina", 63),)},
        "SAXOFONE": {"rjm": (("GIAMPIERI", "pagina", 21), ("RUSSO", "pagina", 25), ("ALMEIDA DIAS", "licao", 13)), "culto": (("GIAMPIERI", "pagina", 30), ("RUSSO", "pagina", 40), ("ALMEIDA DIAS", "licao", 25)), "oficializacao": (("GIAMPIERI", "pagina", 50), ("RUSSO", "pagina", 55))},
        "TROMPETE": {"culto": (("GETCHEL", "licao", 94), ("RUSSO", "pagina", 30), ("ALMEIDA DIAS", "licao", 25)), "oficializacao": (("RUSSO", "pagina", 41),)},
        "TROMPA": {"rjm": (("TROMPA", "licao", 73),), "culto": (("TROMPA", "licao", 105),)},
        "TROMBONE": {"rjm": (("RUBANK", "pagina", 24), ("ALMEIDA DIAS", "licao", 13)), "culto": (("RUBANK", "pagina", 37), ("ALMEIDA DIAS", "licao", 25)), "oficializacao": (("RUBANK", "pagina", 48),)},
    }
    rules["EUFONIO"] = rules["TROMBONE"]
    rules["TUBA"] = rules["TROMBONE"]
    completion_words = ("COMPLETO", "CONCLUIDO", "FINALIZADO")
    for row in rows:
        name = norm(row.get("metodo"))
        detail = norm(" ".join(str(row.get(key) or "") for key in ("pagina", "licao", "observacoes")))
        if any(word in detail for word in completion_words):
            return True
        for alias, field, minimum in rules.get(group, {}).get(target, ()):
            if alias in name and _maximum([row], (field,)) >= minimum:
                return True
    return False

def assess_program(student, records):
    target = target_for_level(student.get("nivel"))
    group = instrument_group(student.get("instrumento"), student.get("cargo_ministerio"))
    if target == "concluido":
        return {"target": target, "target_label": "Formação concluída", "instrument_group": group,
                "status": "completed", "eligible": False, "completion_percent": 100,
                "summary": "Aluno já consta como oficializado.", "requirements": []}
    level = LEVELS[target]
    msa, methods, hymns = records.get("msa") or [], records.get("metodo") or [], records.get("hinario") or []
    msa_current = _maximum(msa, ("fase",))
    msa_required = f"Fase mínima exigida para a etapa: {level['msa_phase']}" + (" com revisão" if level.get("revision") else "")
    msa_detail = f"Fase alcançada no histórico: {msa_current:g}" if msa_current else "Sem fase documentada"
    if group == "ORGAO" and target != "oficializacao":
        lesson_target = 80 if target == "rjm" else 107
        page_target = 110 if target == "rjm" else 135
        lesson_current = _maximum(msa, ("licoes",))
        page_current = _maximum(msa, ("paginas",))
        msa_ok = lesson_current >= lesson_target or page_current >= page_target
        msa_required = f"MSA até lição {lesson_target} / página {page_target}"
        msa_detail = f"Máximo documentado: lição {lesson_current:g}; página {page_current:g}"
    else:
        msa_ok = msa_current >= level["msa_phase"]
    if level.get("revision"):
        msa_ok = msa_ok and any("REVISAO" in norm(" ".join(str(row.get(k) or "") for k in ("fase", "observacoes"))) for row in msa)
    if group != "ORGAO" and msa_current:
        comparison = "requisito atendido" if msa_current == level["msa_phase"] else "requisito superado" if msa_current > level["msa_phase"] else "abaixo do requisito"
        msa_detail = f"Fase alcançada no histórico: {msa_current:g} ({comparison})"
    hymn_set = _documented_hymns(hymns)
    expected_hymns = set(range(level["hymns"][0], level["hymns"][1] + 1))
    hymn_ok = expected_hymns.issubset(hymn_set)
    if group == "ORGAO":
        method_text = {"rjm": "Volumes 1 e 2 completos", "culto": "Volume 3 completo (mais volumes anteriores, se não apresentados)", "oficializacao": "Volume 4 completo"}[target]
        method_matches = [row for row in methods if f"VOL{ {'rjm':' 2','culto':' 3','oficializacao':' 4'}[target]}".replace(" ", "") in norm(row.get("metodo")).replace(" ", "")]
    else:
        method_text = METHOD_PROGRAM.get(group, {}).get(target, "Programa do método específico não cadastrado para este instrumento.")
        method_matches = methods
    method_ok = _method_threshold_met(method_matches, group, target)
    method_status = "ok" if method_ok else "review" if method_matches else "missing"
    requirements = [
        {"area": "MSA", "required": msa_required,
         "current": msa_detail, "status": "ok" if msa_ok else "missing"},
        {"area": "Método", "required": method_text,
         "current": f"{len(methods)} lançamento(s); máximo informado: {_maximum(methods, ('pagina','licao')):g}" if methods else "Sem lançamento documentado",
         "status": method_status},
        {"area": "Hinário", "required": f"Hinos {level['hymns'][0]} a {level['hymns'][1]}" + (" - voz principal" if target == "rjm" else " - voz principal e alternativa"),
         "current": f"{len(hymn_set)} hino(s) distintos documentados", "status": "ok" if hymn_ok else "missing"},
    ]
    completion_percent = round(sum(item["status"] == "ok" for item in requirements) / len(requirements) * 100)
    eligible = completion_percent == 100
    status = "eligible" if eligible else "review" if any(item["status"] == "review" for item in requirements) else "pending"
    summary = "Requisitos documentais atendidos; apto para emissão da carta." if eligible else (
        "Há método lançado, mas a conclusão precisa de validação pedagógica." if status == "review" else
        "Os lançamentos ainda não comprovam todos os requisitos do Programa Mínimo."
    )
    return {"target": target, "target_label": level["label"], "instrument_group": group,
            "status": status, "eligible": eligible, "completion_percent": completion_percent,
            "summary": summary, "requirements": requirements,
            "reference": "Programa Mínimo 2023 - Circular 158/2023"}
