"""Prepara a distribuição oficial sem alterar os cadastros de residência.

Uso: python scripts/importar_assistencias_ministerio.py --snapshot ... --xlsx ...
     --pdf ... --output ...
O resultado é um catálogo de vínculos, nunca instruções extraídas dos documentos.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROLE_LABELS = {"anciao": "Ancião", "regional": "Encarregado Regional", "examinadora": "Examinadora de Organista"}


def norm(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(value or "").upper())
                             if not unicodedata.combining(c)).split())


def code(value):
    match = re.search(r"BR-\d{2}-\d{4}", str(value or ""))
    return match[0] if match else ""


def tokens(value):
    value = re.sub(r"\(\s*ORGANISTA\s*\)", "", str(value or ""), flags=re.I)
    return [v for v in re.findall(r"[A-Z]+", norm(value)) if v not in {"DE", "DA", "DO", "DAS", "DOS"}]


def build(snapshot, spreadsheet, pdf, examiner_workbook=None):
    import openpyxl
    from pypdf import PdfReader
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ColorAdminApp.modules.music_events_identity import CommonResolver

    catalog = [dict(c) for c in snapshot["catalog"]]
    # Correção sustentada pelo código explícito da relação oficial.
    corrections = []
    for common in catalog:
        if norm(common["comum"]) == "BR-21-1251 - CAPELA VELHA - SURU":
            corrections.append({"before": common["comum"], "after": "BR-21-1303 - CAPELA VELHA - SURU"})
            common["comum"] = "BR-21-1303 - CAPELA VELHA - SURU"
    commons = {code(c["comum"]): c for c in catalog}
    resolver = CommonResolver(catalog)
    directory = []
    for source, rows in [("ministerio", snapshot["ministry"]), ("sam", snapshot["sam"])]:
        for row in rows:
            name = row.get("nome") or row.get("nome_aluno")
            raw_role = norm(row.get("ministerio") or row.get("cargo_ministerio"))
            residence = code(row.get("comum") or row.get("comum_congregacao"))
            if residence not in commons:
                continue
            role = "anciao" if raw_role == "ANCIAO" else "regional" if "ENCARREGADO REGIONAL" in raw_role else "examinadora" if "EXAMINADORA" in raw_role else "secretario" if "SECRET" in raw_role and "MUSICA" in raw_role else "outro"
            secretary_label = "Secretária da Música" if (
                "SECRETARIA" in raw_role or "(ORGANISTA)" in norm(name)
                or norm(row.get("instrumento")) in {"ORGAO", "ORGANISTA"}
            ) else "Secretário da Música"
            directory.append(dict(person_id=f"{source}:{row['id']}", nome=name, role=role, secretary_label=secretary_label,
                                  residence_code=residence, city=commons[residence]["cidade"]))
    # Residências expressamente confirmadas pelo usuário nesta tarefa.
    confirmed = {"EDWIL SANTOS NETO": ["BR-22-0673", "BR-21-1039"], "LUCIANO DO NASCIMENTO": ["BR-22-0673"]}
    workbook = openpyxl.load_workbook(spreadsheet, read_only=True, data_only=True)
    source_rows = list(workbook.worksheets[0].values)
    proposed, issues = {}, []

    def match_person(name, role, city, pdf_scope=False):
        wanted = tokens(name)
        eligible = [p for p in directory if p["role"] == role]
        if pdf_scope:
            eligible = [p for p in eligible if norm(p["city"]) in {"SANTANA DE PARNAIBA", "PIRAPORA DO BOM JESUS"}]
        matches = [p for p in eligible if tokens(p["nome"]) == wanted]
        if not matches:
            matches = [p for p in eligible if all(t in tokens(p["nome"]) for t in wanted)]
        # A planilha contém esta variante ortográfica do mesmo ancião.
        if not matches and norm(name) == "EUDER ALTEBARMAKYAN":
            matches = [p for p in eligible if norm(p["nome"]) == "EUDER ALTEBARMAKIAN"]
        named = {" ".join(tokens(p["nome"])) for p in matches}
        if len(named) == 1:
            residences = confirmed.get(norm(matches[0]["nome"]))
            if residences:
                return {**matches[0], "residence_codes": residences}
            residences = {p["residence_code"] for p in matches}
            return {**matches[0], "residence_codes": list(residences) if len(residences) == 1 else []}
        # PDF pode atribuir Secretaria da Música a quem possui outro cargo no SAM.
        # Só conciliar quando há uma única identidade no setor dos dois municípios.
        if not matches and role == "secretario":
            matches = [p for p in directory if p["person_id"].startswith("sam:")
                       and (not pdf_scope or norm(p["city"]) in {"SANTANA DE PARNAIBA", "PIRAPORA DO BOM JESUS"})
                       and all(t in tokens(p["nome"]) for t in wanted)]
            if len({norm(p["nome"]) for p in matches}) == 1:
                return {**matches[0], "residence_codes": [matches[0]["residence_code"]]}
        return None

    def add(target, name, role, document, row, pdf_scope=False):
        name = str(name or "").strip()
        if not name:
            return
        correction = None
        if target == "BR-22-1251" and role == "anciao" and norm(name) == "FLAVIO LUIZ":
            correction = "Correção confirmada pelo usuário: ancião da Central de Santana é Salomão Luiz de Albuquerque."
            name = "SALOMÃO LUIZ DE ALBUQUERQUE"
        common = commons[target]
        person = match_person(name, role, common["cidade"], pdf_scope)
        if not person:
            issues.append(dict(congregation_code=target, nome_informado=name, role=role,
                               source_document=document, source_row=row, motivo="Pessoa não conciliada de forma única"))
            return
        item = dict(congregation_code=target, role=role, person_id=person["person_id"],
                    nome=person["nome"], residence_codes=person["residence_codes"],
                    source_document=document, source_row=row)
        item["role_label"] = person["secretary_label"] if role == "secretario" else ROLE_LABELS[role]
        if correction:
            item["source_correction"] = correction
        proposed.setdefault((target, role), {})[person["person_id"]] = item

    for number, row in enumerate(source_rows[1:], 2):
        target = code(row[2]) if len(row) > 8 else ""
        if target not in commons:
            continue
        for role, column in [("anciao", 3), ("regional", 5), ("secretario", 7)]:
            add(target, row[column], role, spreadsheet.name, number)

    # O PDF é a distribuição específica de Santana/Pirapora e prevalece para
    # os cargos nele informados. Ele não contém a coluna de anciães.
    text = "\n".join(page.extract_text() for page in PdfReader(pdf).pages)
    pattern = re.compile(r"^(\d+)\s+(.+?)\s+(Santana de Parnaíba|Pirapora do Bom Jesus)\s+(Humberto|José dos Reis)\s+(Andréia|Izabel)\s+(.+?)\s+Ir\.?\s*", re.I)
    pdf_rows = 0
    for line in text.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        number, name, city, regional, examiner, secretaries = m.groups()
        aliases = {"CAPELA VELHA": "BR-21-1303", "FAZENDINHA": "BR-22-0272",
                   "JARDIM ITAPUA": "BR-22-3132", "NOVA PIRAPORA - CENTRAL": "BR-22-1074",
                   "PARQUE LARANJEIRAS II": "BR-21-1565"}
        common = commons.get(aliases.get(norm(name))) or resolver.resolve(name, city)
        if not common:
            issues.append(dict(nome_informado=name, source_document=pdf.name, source_row=int(number), motivo="Comum não conciliada"))
            continue
        target = code(common["comum"])
        pdf_rows += 1
        proposed[(target, "regional")] = {}
        proposed[(target, "examinadora")] = {}
        proposed[(target, "secretario")] = {}
        issues[:] = [i for i in issues if not (i.get("congregation_code") == target and i.get("role") in {"regional", "secretario"})]
        add(target, regional, "regional", pdf.name, int(number), True)
        add(target, examiner, "examinadora", pdf.name, int(number), True)
        for secretary in secretaries.split("/"):
            add(target, secretary, "secretario", pdf.name, int(number), True)
    if pdf_rows != 41:
        raise ValueError(f"Esperadas 41 comuns no PDF; conciliadas {pdf_rows}.")
    examiner_workbook_codes = set()
    if examiner_workbook:
        book = openpyxl.load_workbook(examiner_workbook, read_only=True, data_only=True)
        for sheet in book:
            columns = None
            for number, row in enumerate(sheet.values, 1):
                if columns is None:
                    headers = {norm(value): index for index, value in enumerate(row) if value}
                    if "EXAMINADORA" in headers and "COMUM" in headers:
                        columns = headers
                    continue
                target = code(row[columns["COMUM"]])
                if not target:
                    continue
                if target not in commons:
                    raise ValueError(f"Comum da planilha de examinadoras não encontrada: {target}.")
                if target not in examiner_workbook_codes:
                    proposed[(target, "examinadora")] = {}
                examiner_workbook_codes.add(target)
                for name in re.split(r"[/;]+", str(row[columns["EXAMINADORA"]] or "")):
                    add(target, name, "examinadora", examiner_workbook.name, number)
        if not examiner_workbook_codes:
            raise ValueError("A planilha não contém uma tabela de comuns e examinadoras.")
    # Manter todos os residentes atuais: a distribuição de atendimento não
    # remove um segundo residente quando a planilha informa só um responsável.
    for person in directory:
        if person["role"] not in {"anciao", "regional", "examinadora", "secretario"}:
            continue
        target = person["residence_code"]
        canonical_person = match_person(person["nome"], person["role"], person["city"])
        if not canonical_person or target not in canonical_person["residence_codes"]:
            continue
        item = dict(congregation_code=target, role=person["role"], person_id=canonical_person["person_id"],
                    nome=person["nome"], residence_codes=canonical_person["residence_codes"], source_document="Cadastro atual / residência", source_row=None)
        item["role_label"] = person["secretary_label"] if person["role"] == "secretario" else ROLE_LABELS[person["role"]]
        proposed.setdefault((target, person["role"]), {}).setdefault(canonical_person["person_id"], item)
    assignments = [i for group in proposed.values() for i in group.values()]
    assignments.sort(key=lambda i: (i["congregation_code"], i["role"], norm(i["nome"])))
    source_paths = [spreadsheet, pdf] + ([examiner_workbook] if examiner_workbook else [])
    return dict(schema_version=1, sources=[dict(name=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in source_paths],
                pdf_commons=pdf_rows, examiner_workbook_commons=len(examiner_workbook_codes), catalog_corrections=corrections, assignments=assignments, pending=issues)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ["snapshot", "xlsx", "pdf", "output"]:
        parser.add_argument(f"--{argument}", type=Path, required=True)
    parser.add_argument("--merge-role", choices=["examinadora"])
    parser.add_argument("--examiner-workbook", type=Path)
    args = parser.parse_args()
    result = build(json.loads(args.snapshot.read_text(encoding="utf-8")), args.xlsx, args.pdf, args.examiner_workbook)
    if args.merge_role:
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        result["assignments"] = ([a for a in previous["assignments"] if a["role"] != args.merge_role]
                                  + [a for a in result["assignments"] if a["role"] == args.merge_role])
        result["pending"] = ([a for a in previous.get("pending", []) if a.get("role") != args.merge_role]
                             + [a for a in result["pending"] if a.get("role") == args.merge_role])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"assignments": len(result["assignments"]), "pending": len(result["pending"]), "pdf_commons": result["pdf_commons"]}))
