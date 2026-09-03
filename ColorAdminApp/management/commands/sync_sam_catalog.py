import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import common_catalog, service_headers
from ColorAdminApp.sam_catalog import norm, parse_catalog


class Command(BaseCommand):
    help = "Concilia o catálogo SAM, detecta novos alunos e registra mudanças de nível."

    def add_arguments(self, parser):
        parser.add_argument("input", type=Path)
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--report", type=Path)

    def _all(self, table, select="*"):
        url = f"{settings.SUPABASE_URL}/rest/v1/{table}"
        count_response = requests.get(
            url, headers=service_headers("count=exact"),
            params={"select": "id", "limit": 1}, timeout=30,
        )
        count_response.raise_for_status()
        try:
            total = int(count_response.headers.get("Content-Range", "0/0").rsplit("/", 1)[-1])
        except ValueError:
            total = 10000

        def fetch(offset):
            response = requests.get(
                url, headers=service_headers(),
                params={"select": select, "offset": offset, "limit": 1000}, timeout=30,
            )
            response.raise_for_status()
            return offset, response.json()

        offsets = list(range(0, total, 1000))
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(offsets)))) as executor:
            pages = sorted(executor.map(fetch, offsets), key=lambda item: item[0])
        return [row for _, batch in pages for row in batch]

    def _post(self, table, payload, prefer="return=representation"):
        response = requests.post(
            f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers(prefer),
            json=payload, timeout=45,
        )
        response.raise_for_status()
        return response.json() if response.content else []

    def _patch(self, table, row_id, payload):
        response = requests.patch(
            f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers("return=minimal"),
            params={"id": f"eq.{row_id}"}, json=payload, timeout=30,
        )
        response.raise_for_status()

    def _upsert_states(self, rows):
        for start in range(0, len(rows), 200):
            response = requests.post(
                f"{settings.SUPABASE_URL}/rest/v1/sam_student_sync_state",
                headers=service_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "source_key"}, json=rows[start:start + 200], timeout=45,
            )
            response.raise_for_status()

    @staticmethod
    def _missing_states(states, observed_keys):
        observed = {str(key) for key in observed_keys}
        return [state for state in states if str(state.get("source_key")) not in observed]

    @staticmethod
    def _catalog_size_is_safe(discovered, previous_active, minimum_ratio=0.8):
        return not previous_active or discovered >= max(1, int(previous_active * minimum_ratio))

    def handle(self, *args, **options):
        path = options["input"]
        if not path.is_file():
            raise CommandError(f"Catálogo não encontrado: {path}")
        try:
            students = parse_catalog(json.loads(path.read_text(encoding="utf-8-sig")))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise CommandError(f"Catálogo inválido: {exc}") from exc
        if not students:
            raise CommandError("O SAM não devolveu alunos; sincronização cancelada para proteger a base.")

        try:
            targets = self._all(
                "musica_acompanhamento_aluno",
                "id,nome_aluno,comum_congregacao,municipio,instrumento,nivel,cargo_ministerio,status",
            )
            states = self._all("sam_student_sync_state") if options["commit"] else []
            commons = common_catalog()
        except requests.RequestException as exc:
            raise CommandError(
                "Falha ao consultar o Supabase. Confirme se a migração 012 foi aplicada antes do modo --commit: " + str(exc)
            ) from exc

        state_by_key = {str(row.get("source_key")): row for row in states}
        target_by_id = {str(row.get("id")): row for row in targets}
        targets_by_name = {}
        for row in targets:
            targets_by_name.setdefault(norm(row.get("nome_aluno")), []).append(row)
        commons_by_location = {}
        for row in commons:
            description = str(row.get("comum") or "").split(" - ", 1)[-1]
            commons_by_location.setdefault((norm(description), norm(row.get("cidade"))), []).append(row)
        now = datetime.now(timezone.utc).isoformat()
        observed_keys = {student["source_key"] for student in students}
        previous_active = sum(1 for state in states if not state.get("missing_since"))
        if options["commit"] and not self._catalog_size_is_safe(len(students), previous_active):
            raise CommandError(
                f"Catálogo SAM possivelmente incompleto: {len(students)} alunos recebidos para "
                f"{previous_active} estados ativos. Nenhum estado foi alterado."
            )
        missing_states = self._missing_states(states, observed_keys)
        stats, changes, unresolved, state_upserts = Counter(), [], [], []
        run_id = None
        if options["commit"]:
            run_id = self._post("sam_sync_runs", {"status": "running", "discovered_students": len(students)})[0]["id"]

        try:
            if options["commit"]:
                new_payloads = []
                for student in students:
                    state = state_by_key.get(student["source_key"]) or {}
                    if state.get("aluno_id") or targets_by_name.get(norm(student["name"])):
                        continue
                    common_matches = commons_by_location.get((norm(student["common_name"]), norm(student["city"])), [])
                    if len(common_matches) != 1:
                        continue
                    local_common = common_matches[0]
                    new_payloads.append({
                        "nome_aluno": student["name"], "status": "Ativo", "registro_msa": student["source_key"],
                        "comum_congregacao": local_common["comum"], "municipio": local_common.get("cidade"),
                        "cargo_ministerio": student["ministry"], "nivel": student["level"],
                        "instrumento": student["instrument"],
                    })
                for start in range(0, len(new_payloads), 200):
                    created_rows = self._post("musica_acompanhamento_aluno", new_payloads[start:start + 200])
                    for target in created_rows:
                        targets.append(target)
                        target_by_id[str(target["id"])] = target
                        targets_by_name.setdefault(norm(target.get("nome_aluno")), []).append(target)
                stats["new_students"] = len(new_payloads)

            patch_jobs = []
            for student in students:
                state = state_by_key.get(student["source_key"]) or {}
                target = target_by_id.get(str(state.get("aluno_id"))) if state.get("aluno_id") else None
                named = targets_by_name.get(norm(student["name"]), []) if not target else []
                match_status = "linked" if target else "matched_name" if len(named) == 1 else "unmatched" if not named else "ambiguous"
                target = target or (named[0] if len(named) == 1 else None)
                if target:
                    stats[match_status] += 1
                common_matches = commons_by_location.get((norm(student["common_name"]), norm(student["city"])), [])
                local_common = common_matches[0] if len(common_matches) == 1 else None
                is_changed = state.get("source_fingerprint") != student["fingerprint"]
                previous_level = state.get("source_level")

                if not target and match_status == "unmatched" and local_common:
                    if not options["commit"]:
                        stats["new_students"] += 1
                if not target:
                    stats[match_status] += 1
                    unresolved.append({"source_key": student["source_key"], "name": student["name"], "reason": match_status})

                target_id = target.get("id") if target else None
                if target and is_changed:
                    update = {}
                    for source_field, target_field in (
                        ("instrument", "instrumento"), ("level", "nivel"), ("ministry", "cargo_ministerio")
                    ):
                        source_value = student[source_field]
                        if source_field == "instrument" and norm(source_value) == "A DEFINIR" and target.get(target_field):
                            continue
                        if source_value and source_value != (target.get(target_field) or ""):
                            update[target_field] = source_value
                    if local_common and local_common["comum"] != target.get("comum_congregacao"):
                        update.update({"comum_congregacao": local_common["comum"], "municipio": local_common.get("cidade")})
                    if update:
                        changes.append({"source_key": student["source_key"], "aluno_id": target_id, "fields": update})
                        stats["changed_students"] += 1
                        if options["commit"]:
                            patch_jobs.append((target_id, update))

                if target and previous_level and previous_level != student["level"]:
                    stats["level_changes"] += 1
                    if options["commit"]:
                        self._post("sam_level_history", {
                            "aluno_id": target_id, "sync_state_id": state.get("id"),
                            "previous_level": previous_level, "new_level": student["level"],
                            "effective_at": now, "source_date": None, "date_basis": "detected_at_sync",
                            "detected_at": now, "sync_run_id": run_id,
                            "evidence": {"source_key": student["source_key"], "catalog_fingerprint": student["fingerprint"]},
                        }, "return=minimal")

                if options["commit"]:
                    history_is_current = bool(state.get("last_history_sync_at")) and not is_changed
                    sync_status = "synced" if target and history_is_current else "pending" if target else match_status
                    state_payload = {
                        "source_key": student["source_key"], "aluno_id": target_id,
                        "source_name": student["name"], "source_common": student["common_name"],
                        "source_instrument": student["instrument"], "source_level": student["level"],
                        "source_fingerprint": student["fingerprint"], "last_seen_at": now,
                        "last_changed_at": now if is_changed else state.get("last_changed_at") or now,
                        "missing_since": None, "sync_status": sync_status, "last_error": None,
                        "source_payload": student, "updated_at": now,
                    }
                    state_upserts.append(state_payload)

            if options["commit"] and patch_jobs:
                self.stdout.write(f"Aplicando {len(patch_jobs)} atualizações de alunos em paralelo...")
                with ThreadPoolExecutor(max_workers=min(8, len(patch_jobs))) as executor:
                    list(executor.map(lambda job: self._patch("musica_acompanhamento_aluno", job[0], job[1]), patch_jobs))
            if options["commit"]:
                self.stdout.write(f"Gravando {len(state_upserts)} estados SAM em lotes...")
                self._upsert_states(state_upserts)
                newly_missing = [state for state in missing_states if not state.get("missing_since")]
                if newly_missing:
                    self.stdout.write(f"Marcando {len(newly_missing)} aluno(s) ausente(s) do catálogo atual...")
                    with ThreadPoolExecutor(max_workers=min(8, len(newly_missing))) as executor:
                        list(executor.map(
                            lambda state: self._patch("sam_student_sync_state", state["id"], {
                                "missing_since": now,
                                "last_error": None,
                                "updated_at": now,
                            }),
                            newly_missing,
                        ))

            stats["catalog_students"] = len(students)
            stats["missing_students"] = len(missing_states)
            report = {"mode": "commit" if options["commit"] else "preview", "statistics": dict(stats), "changes": changes, "unresolved": unresolved}
            if options.get("report"):
                options["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(json.dumps(report["statistics"], ensure_ascii=False, indent=2))
            if options["commit"]:
                self._patch("sam_sync_runs", run_id, {
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "partial" if unresolved else "success",
                    "changed_students": stats["changed_students"], "error_count": len(unresolved),
                    "details": {"new_students": stats["new_students"], "level_changes": stats["level_changes"]},
                })
            else:
                self.stdout.write(self.style.WARNING("Prévia concluída; nenhuma alteração foi gravada."))
        except Exception as exc:
            if options["commit"] and run_id:
                try:
                    self._patch("sam_sync_runs", run_id, {
                        "finished_at": datetime.now(timezone.utc).isoformat(), "status": "failed",
                        "error_count": 1, "details": {"error": str(exc)[:1000]},
                    })
                except Exception:
                    pass
            raise CommandError(f"Sincronização interrompida: {exc}") from exc
