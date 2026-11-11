"""Importação idempotente: nunca sobrescreve distribuições já gravadas."""
from collections import defaultdict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from ColorAdminApp import admin_views


class Command(BaseCommand):
    help = "Importa a distribuição oficial conciliada de residentes e assistências. Padrão: simulação."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--actor-id", default=None)
        parser.add_argument("--add-role", choices=["examinadora"])
        parser.add_argument("--refresh-role-in-administration", choices=["cotia_caucaia_vgp", "itapevi", "jandira", "santana_pirapora"])

    def handle(self, *args, **options):
        module = admin_views.congregation_distribution
        if options["refresh_role_in_administration"] and not options["add_role"]:
            raise CommandError("Informe --add-role para atualizar uma distribuição por administração.")
        seed = module.seed()
        if seed.get("pending"):
            raise CommandError("Há identidades pendentes de conciliação; importação interrompida.")
        existing, editable = module.load_overrides(admin_views._get_table)
        if not editable:
            raise CommandError("Execute scripts/migrations/053_congregation_distribution.sql antes de importar.")
        if options["add_role"]:
            return self.add_role(module, seed, existing, options)
        known = {row["congregation_code"] for row in existing}
        grouped = defaultdict(list)
        for item in seed["assignments"]:
            grouped[item["congregation_code"]].append(item)
        now = datetime.now(timezone.utc).isoformat()
        payload = [{"congregation_code": code, "assignments": items, "revision": 1,
                    "updated_by": options["actor_id"] or "importacao_relacao_oficial",
                    "updated_at": now}
                   for code, items in grouped.items() if code not in known]
        self.stdout.write(f"Comuns novas: {len(payload)}; preservadas: {len(known)}; vínculos novos: {sum(len(p['assignments']) for p in payload)}.")
        if not options["apply"] or not payload:
            return
        response = requests.post(
            f"{settings.SUPABASE_URL}/rest/v1/{module.TABLE}",
            headers=admin_views._headers("resolution=ignore-duplicates,return=representation"),
            params={"on_conflict": "congregation_code"}, json=payload, timeout=30,
        )
        response.raise_for_status()
        created = response.json()
        after, _ = module.load_overrides(admin_views._get_table)
        after_codes = {row["congregation_code"] for row in after}
        if not set(grouped).issubset(after_codes):
            raise CommandError("O banco não confirmou todas as comuns importadas.")
        request = RequestFactory().post("/management/import_congregation_distribution/")
        request.session = {"user_id": options["actor_id"], "user_profile": {"full_name": "Importação da distribuição oficial"}}
        admin_views.log_audit(request, "IMPORT", "ADMINISTRACAO_CONGREGACOES", {
            "entity": module.TABLE, "created_commons": len(created),
            "assignment_count": sum(len(row["assignments"]) for row in created),
            "source_documents": seed["sources"], "outcome": "success",
        })
        self.stdout.write(self.style.SUCCESS(f"Importação confirmada: {len(created)} comuns. Cadastros de origem preservados."))

    def add_role(self, module, seed, existing, options):
        role = options["add_role"]
        refresh_group = options["refresh_role_in_administration"]
        groups = {}
        if refresh_group:
            groups = {module.common_code(c["comum"]): module.administration(c.get("cidade") or c.get("municipio"))
                      for c in module.corrected_catalog(admin_views.common_catalog())}
        grouped = defaultdict(list)
        for item in seed["assignments"]:
            if item["role"] == role:
                grouped[item["congregation_code"]].append(item)
        by_code = {row["congregation_code"]: row for row in existing}
        pending = []
        for code, items in grouped.items():
            if refresh_group and groups.get(code) != refresh_group:
                continue
            before = by_code.get(code)
            if not before:
                raise CommandError("Execute a importação inicial antes de complementar os cargos.")
            current = [a for a in before["assignments"] if a["role"] == role]
            signature = lambda values: sorted((a["person_id"], sorted(a.get("residence_codes", []))) for a in values)
            if (refresh_group and signature(current) != signature(items)) or (not refresh_group and not current):
                pending.append((before, items))
        self.stdout.write(f"Atualizações: {len(pending)} comuns; vínculos de examinadoras: {sum(len(i) for _, i in pending)}. Os outros cargos serão preservados.")
        if not options["apply"] or not pending:
            return

        def write(entry):
            before, items = entry
            kept = [a for a in before["assignments"] if not refresh_group or a["role"] != role]
            payload = {"assignments": kept + items, "revision": before["revision"] + 1,
                       "updated_by": options["actor_id"] or "complemento_examinadoras",
                       "updated_at": datetime.now(timezone.utc).isoformat()}
            response = requests.patch(
                f"{settings.SUPABASE_URL}/rest/v1/{module.TABLE}", headers=admin_views._headers("return=representation"),
                params={"congregation_code": f"eq.{before['congregation_code']}", "revision": f"eq.{before['revision']}"},
                json=payload, timeout=30,
            )
            response.raise_for_status()
            confirmed = response.json()
            if not confirmed:
                raise CommandError(f"A comum {before['congregation_code']} foi alterada durante a importação. Execute novamente.")
            return {"congregation_code": before["congregation_code"], "before": before, "after": confirmed[0]}

        changes, failures = [], []
        with ThreadPoolExecutor(max_workers=4) as executor:
            for future in as_completed([executor.submit(write, entry) for entry in pending]):
                try:
                    changes.append(future.result())
                except (requests.RequestException, CommandError) as exc:
                    failures.append(str(exc))
        request = RequestFactory().post("/management/import_congregation_distribution/")
        request.session = {"user_id": options["actor_id"], "user_profile": {"full_name": "Complemento da distribuição de examinadoras"}}
        admin_views.log_audit(request, "IMPORT", "ADMINISTRACAO_CONGREGACOES", {
            "entity": module.TABLE, "role": role,
            "changes": [{"congregation_code": change["congregation_code"],
                         "before_revision": change["before"]["revision"], "after_revision": change["after"]["revision"],
                         "before": change["before"]["assignments"], "after": change["after"]["assignments"]}
                        for change in changes],
            "source_documents": seed["sources"],
            "outcome": "partial" if failures else "success", "failures": failures,
        })
        if failures:
            raise CommandError("Algumas comuns não foram atualizadas: " + "; ".join(failures))
        self.stdout.write(self.style.SUCCESS(f"Complemento confirmado: {len(changes)} comuns; outros cargos preservados."))
