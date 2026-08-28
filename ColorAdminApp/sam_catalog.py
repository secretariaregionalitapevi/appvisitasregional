import html
import re
import unicodedata
from hashlib import sha256
import json


def norm(value):
    text = unicodedata.normalize("NFKD", html.unescape(str(value or "")))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).upper().split())


def clean_html(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())


def parse_catalog(document):
    students = []
    seen = set()
    for raw in document.get("rows") or []:
        cells = raw.get("cells") or []
        if len(cells) < 6:
            continue
        source_key = clean_html(cells[0])
        name = clean_html(cells[1])
        if not source_key or not name or source_key in seen:
            continue
        seen.add(source_key)
        common_raw = clean_html(cells[2])
        common_name, _, regional_code = common_raw.partition("|")
        regional_code = regional_code.strip()
        city = regional_code.rsplit("-", 1)[-1].strip() if regional_code else ""
        student = {
            "source_key": source_key,
            "name": name,
            "common_name": common_name.strip(),
            "regional_code": regional_code,
            "city": city,
            "ministry": clean_html(cells[3]),
            "instrument": clean_html(cells[4]),
            "level": clean_html(cells[5]),
        }
        serialized = json.dumps(student, ensure_ascii=False, sort_keys=True)
        student["fingerprint"] = sha256(serialized.encode("utf-8")).hexdigest()
        students.append(student)
    return students


def match_local_common(student, commons):
    wanted_name, wanted_city = norm(student.get("common_name")), norm(student.get("city"))
    matches = []
    for row in commons:
        common = str(row.get("comum") or "")
        description = common.split(" - ", 1)[-1]
        if norm(description) != wanted_name:
            continue
        if wanted_city and norm(row.get("cidade")) != wanted_city:
            continue
        matches.append(row)
    return matches[0] if len(matches) == 1 else None


def match_target(student, targets, linked_id=None):
    if linked_id:
        linked = [row for row in targets if str(row.get("id")) == str(linked_id)]
        if len(linked) == 1:
            return linked[0], "linked"
    named = [row for row in targets if norm(row.get("nome_aluno")) == norm(student.get("name"))]
    if len(named) == 1:
        return named[0], "matched_name"
    return None, "unmatched" if not named else "ambiguous"
