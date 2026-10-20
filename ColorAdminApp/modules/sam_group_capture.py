"""Cadastro completo de turmas: leitura no SAM, escrita apenas no espelho pessoal."""
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from .sam_class_mirror import BASE_URL, fetch_text, fetch_group_page, parse_group_row, fingerprint, _slash_date

FIELDS = ("id_curso", "descricao", "id_igreja", "dia_semana", "dt_inicio", "dt_fim",
          "hr_inicio", "hr_fim", "id_responsavel", "id_responsavel2", "id_turma_genero", "status")


def parse_registration(html, source_id):
    soup = BeautifulSoup(html, "html.parser")
    form = next((f for f in soup.find_all("form") if "/turmas/atualizar" in (f.get("action") or "") or "/turmas/salvar" in (f.get("action") or "")), None)
    if form is None:
        raise ValueError("Cadastro de turma indisponível; os dados anteriores foram preservados")
    result, labels = {}, {}
    for name in FIELDS:
        field = form.find(attrs={"name": name})
        if field is None:
            raise ValueError("Campo esperado ausente: " + name)
        if field.name == "select":
            selected = field.find("option", selected=True)
            if selected is None:
                selected = field.find("option")
            result[name] = selected.get("value", "") if selected else ""
            labels[name] = selected.get_text(" ", strip=True) if selected else ""
        elif field.get("type") == "checkbox":
            result[name] = field.get("value", "1") if field.has_attr("checked") else "0"
        else:
            result[name] = field.get("value", "")
    # Select2 insere os responsáveis a partir de uma opção declarada no script.
    for script in soup.find_all("script"):
        text = script.get_text()
        for match in re.finditer(r"(?:const|let|var)\s+(\w+)\s*=\s*(['\"])(<option\b.*?</option>)\2", text, re.S):
            variable, markup = match.group(1), match.group(3)
            for name in ("id_responsavel", "id_responsavel2"):
                if re.search(r"\$\(\s*['\"]#" + name + r"['\"]\s*\)\.append\(\s*" + re.escape(variable) + r"\s*\)", text):
                    option = BeautifulSoup(markup, "html.parser").find("option")
                    if option:
                        result[name] = option.get("value", "")
                        labels[name] = option.get_text(" ", strip=True)
    if not result["descricao"] or not result["id_igreja"] or not result["id_curso"]:
        raise ValueError("Identidade da turma incompleta")
    identity = form.find(attrs={"name": "id"})
    if identity and str(identity.get("value")) != str(source_id):
        raise ValueError("Identificador do formulário diverge da turma solicitada")
    for field in ("dt_inicio", "dt_fim"):
        if result[field] and not _slash_date(result[field]):
            raise ValueError("Data inválida no cadastro: " + field)
    missing = [name for name in FIELDS if name not in ("id_responsavel2", "status") and result[name] == ""]
    return {"complete": not missing, "missing_fields": missing, "schema_version": 1, "source_id": str(source_id), "fields": result, "labels": labels,
            "captured_at": datetime.now(timezone.utc).isoformat(), "provenance": "SAM /turmas/editar"}


def read_groups(page):
    """Conferir os dois estados; status=0 sozinho não representa todo o acervo."""
    listing, total = {}, None
    for status in (0, 1):
        expected, start, seen = None, 0, set()
        while True:
            batch = fetch_group_page(page, start, 5000, status=status)
            raw = batch.get("data")
            count = int(batch["recordsFiltered"])
            global_count = int(batch.get("recordsTotal", count))
            if total is not None and total != global_count:
                raise ValueError("Contagem geral alterada durante a consulta")
            total = global_count
            if not isinstance(raw, list) or (expected is not None and count != expected):
                raise ValueError("Listagem incompleta ou alterada; nenhuma atualização iniciada")
            expected = count
            for row in raw:
                parsed = parse_group_row(row)
                if not parsed or parsed["source_id"] in seen:
                    raise ValueError("Identidade ausente ou duplicada na listagem")
                source_id = parsed["source_id"]
                if source_id in listing and listing[source_id] != parsed:
                    raise ValueError("Cadastro alterado entre as duas listagens")
                seen.add(source_id); listing[source_id] = parsed
            start += len(raw)
            if start == expected:
                break
            if not raw or start > expected:
                raise ValueError("Contagem da listagem divergente")
    if len(listing) != total:
        raise ValueError("A união das listagens não cobre a contagem geral; atualização bloqueada")
    return listing


def sync_groups(command, page, force=False):
    existing = {str(r["source_id"]): r for r in command._get_all("sam_gem_groups")}
    listing = read_groups(page)
    all_ids = sorted(set(existing) | set(listing), key=int)
    ids = []
    for source_id in all_ids:
        registration = ((existing.get(source_id) or {}).get("source_payload") or {}).get("registration")
        fresh = False
        if registration and not force:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(registration["captured_at"])).total_seconds()
                current_hash = (listing.get(source_id) or {}).get("source_hash")
                fresh = 0 <= age < 86400 and registration.get("listing_hash") == current_hash
            except (KeyError, ValueError, TypeError):
                pass
        if not fresh:
            ids.append(source_id)
    failures, updated, pending = [], 0, []
    fetched = {}
    for index, source_id in enumerate(ids, 1):
        if (index - 1) % 4 == 0:
            chunk = ids[index-1:index+3]
            responses = page.evaluate("""async ids => await Promise.all(ids.map(async id => {
                try {
                    const response = await fetch('/turmas/editar/' + id, {credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}});
                    return {id,ok:response.ok,html:await response.text(),status:response.status};
                } catch(e) {return {id,ok:false,status:'network'};}
            }))""", chunk)
            fetched = {r["id"]:r for r in responses}
        previous = existing.get(source_id) or {}
        group = dict(listing.get(source_id) or {k: previous.get(k) for k in
                     ("source_id", "congregacao", "curso", "turma", "matriculados", "data_inicio", "data_termino", "dia_horario", "ativo")})
        try:
            response = fetched[source_id]
            if not response["ok"]:
                raise ValueError("Cadastro indisponível: " + str(response["status"]))
            html = response["html"]
            registration = parse_registration(html, source_id)
            registration["listing_hash"] = (listing.get(source_id) or {}).get("source_hash")
            fields = registration["fields"]
            # Nome diferente exige conferir a listagem; não enriquecer outra turma.
            if listing.get(source_id) and fields["descricao"] != group["turma"]:
                raise ValueError("Descrição divergente entre cadastro e listagem")
            payload = dict(previous.get("source_payload") or {})
            payload.update({"registration": registration})
            payload.pop("backfilled", None)
            group.update(data_inicio=_slash_date(fields["dt_inicio"]), data_termino=_slash_date(fields["dt_fim"]),
                         ativo=fields["status"] == "1", source_payload=payload)
            now = registration["captured_at"]
            group.update(source_id=int(source_id), last_seen_at=now, synced_at=now)
            group["source_hash"] = fingerprint({k:v for k,v in group.items() if k not in ("last_seen_at", "synced_at", "source_hash")})
            pending.append(group)
        except Exception as exc:
            failures.append({"source_id": source_id, "reason": type(exc).__name__ + ": " + str(exc)[:200]})
        if index % 50 == 0 or index == len(ids):
            if pending:
                command._upsert("sam_gem_groups", pending, "source_id")
                updated += len(pending); pending = []
            command.stdout.write(f"Cadastro de turmas: {index}/{len(ids)} consultadas, {updated} atualizadas, {len(failures)} pendentes.")
    return {"accessible_listing": len(listing), "registered": len(existing), "updated": updated, "recent_unchanged": len(all_ids) - len(ids),
            "failures": failures, "sam_write_enabled": False}
