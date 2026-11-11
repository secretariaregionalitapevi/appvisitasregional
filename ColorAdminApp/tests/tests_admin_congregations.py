import json
from unittest.mock import patch

import requests
from django.test import RequestFactory, SimpleTestCase

from ColorAdminApp import admin_views


class CongregationAdministrationTests(SimpleTestCase):
    code = "BR-21-0797"

    def setUp(self):
        self.factory = RequestFactory()
        seed_patch = patch.object(admin_views.congregation_distribution, "seed", return_value={"assignments": [], "pending": [], "catalog_corrections": []})
        seed_patch.start()
        self.addCleanup(seed_patch.stop)

    def response(self, status, payload):
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        return response

    def request(self, method, body=None, role=1):
        request = getattr(self.factory, method)(
            f"/administracao/api/operacional/congregacoes/{self.code}/",
            data=json.dumps(body or {}),
            content_type="application/json",
        )
        request.session = {"user_id": "actor", "user_profile": {"role_id": role}}
        return request

    @patch.object(admin_views, "common_catalog")
    @patch.object(admin_views, "_get_table")
    def test_congregation_overrides_are_applied_and_archived_rows_are_optional(self, get_table, catalog):
        catalog.return_value = [{
            "comum": f"{self.code} - NOME ORIGINAL",
            "cidade": "SANTANA DE PARNAÍBA",
        }]
        ministry = [{"id": "person-1", "nome_aluno": "Secretária", "cargo_ministerio": "Secretária da Música",
                     "comum_congregacao": f"{self.code} - NOME ORIGINAL", "municipio": "SANTANA DE PARNAÍBA"}]
        settings = [{"congregation_code": self.code, "nome": "NOME ATUALIZADO", "municipio": "PIRAPORA",
                     "administracao": "REGIONAL", "archived_at": "2026-11-10T00:00:00Z"}]
        get_table.side_effect = lambda table, params: ministry if table == "musica_acompanhamento_aluno" else settings if table == "administrative_congregation_settings" else []

        self.assertEqual(admin_views._congregation_rows(), [])
        row = admin_views._congregation_rows(include_archived=True)[0]
        self.assertEqual(row["nome"], "NOME ATUALIZADO")
        self.assertEqual(row["municipio"], "PIRAPORA")
        self.assertEqual(row["administracao"], "REGIONAL")
        self.assertTrue(row["arquivada"])
        self.assertEqual(row["servos"][0]["nome"], "Secretária")

    @patch.object(admin_views, "common_catalog", return_value=[{
        "comum": f"{code} - CENTRAL", "cidade": "SANTANA DE PARNAÍBA",
    } for code in ["BR-21-0797"]])
    @patch.object(admin_views, "_get_table")
    def test_congregation_data_loads_people_and_overrides_together(self, get_table, catalog):
        source_rows = {
            "administrative_congregation_distribution": [],
            "ministerio_regional": [],
            "administrative_congregation_settings": [{
                "congregation_code": self.code,
                "nome": f"{self.code} - NOME ATUALIZADO", "municipio": "PIRAPORA",
                "administracao": "REGIONAL", "archived_at": None,
                "encarregados_locais": ["irmandade:stale-person"],
            }],
            "musica_acompanhamento_aluno": [{
                "id": "local-1", "nome_aluno": "Encarregado local",
                "comum_congregacao": f"{self.code} - CENTRAL",
                "municipio": "SANTANA DE PARNAIBA", "cargo_ministerio": "ENCARREGADO_LOCAL",
            }],
        }
        get_table.side_effect = lambda table, params: source_rows[table]

        rows, people = admin_views._congregation_data(
            include_archived=True,
            include_people=True,
        )

        self.assertEqual(rows[0]["nome"], f"{self.code} - NOME ATUALIZADO")
        self.assertEqual(rows[0]["municipio"], "PIRAPORA")
        self.assertEqual(len(people), 1)
        self.assertEqual(rows[0]["responsaveis_sistema"][0]["nome"], "Encarregado local")
        self.assertEqual(rows[0]["responsaveis_sistema"][0]["categoria"], "encarregados_locais")
        self.assertEqual(get_table.call_count, len(source_rows))
        self.assertEqual(rows[0]["quantidade_servos"], 1)
        self.assertEqual(rows[0]["distribuicao"]["encarregados_locais"], ["sam:local-1:5"])
        self.assertEqual({call.args[0] for call in get_table.call_args_list}, set(source_rows))

    @patch.object(admin_views, "log_audit")
    @patch.object(admin_views.requests, "post")
    @patch.object(admin_views, "_get_table", return_value=[])
    @patch.object(admin_views, "common_catalog")
    def test_edit_upserts_only_admin_owned_fields(self, catalog, get_table, post, audit):
        catalog.return_value = [{"comum": f"{self.code} - ORIGINAL", "cidade": "SANTANA DE PARNAÍBA"}]
        updated = {
            "congregation_code": self.code,
            "nome": "NOME REVISADO",
            "municipio": "PIRAPORA",
            "administracao": "REGIONAL",
            "archived_at": None,
        }
        post.return_value = self.response(201, [updated])

        response = admin_views.congregation_record(
            self.request("patch", {"nome": "NOME REVISADO", "municipio": "PIRAPORA", "administracao": "REGIONAL"}),
            self.code,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_args.kwargs["params"], {"on_conflict": "congregation_code"})
        self.assertEqual(post.call_args.kwargs["json"]["congregation_code"], self.code)
        self.assertEqual(post.call_args.kwargs["json"]["nome"], "NOME REVISADO")
        self.assertEqual(post.call_args.kwargs["json"]["municipio"], "PIRAPORA")
        get_table.assert_called_once()
        audit.assert_called_once()

    def sam_person(self, identity="1", role="Anci\u00e3o", name="Servo", common=None, city="ITAPEVI"):
        return {"id": identity, "nome_aluno": name, "cargo_ministerio": role,
                "comum_congregacao": common or f"{self.code} - CENTRAL", "municipio": city}

    def test_only_institutional_roles_are_included_in_hierarchy(self):
        catalog = [{"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"}]
        roles = ["SECRETARIO DO GEM", "MUSICO", "ENCARREGADO_LOCAL", "EXAMINADORA",
                 "Anci\u00e3o", "Di\u00e1cono", "Cooperador Of\u00edcio Ministerial",
                 "Cooperador de Jovens e Menores", "Encarregado Regional", "Secretaria da Musica"]
        people = admin_views._congregation_people([
            self.sam_person(str(i), role) for i, role in enumerate(roles)
        ], catalog)
        self.assertEqual(len(people), 9)
        self.assertEqual([admin_views._ministry_rank(p["ministerio"]) for p in people], sorted(
            admin_views._ministry_rank(p["ministerio"]) for p in people))
        self.assertEqual({p["source"] for p in people}, {"sam"})

    def test_duplicate_names_and_role_aliases_are_not_repeated(self):
        catalog = [{"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"}]
        people = admin_views._congregation_people([
            self.sam_person("1", "ENCARREGADO_LOCAL", "JOSE"),
            self.sam_person("2", "Encarregado local", "Jos\u00e9"),
            self.sam_person("3", "Grupo de visitas", "Outra pessoa"),
        ], catalog)
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["categoria"], "encarregados_locais")

    def test_unknown_code_never_falls_back_to_matching_name(self):
        catalog = [{"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"}]
        people = admin_views._congregation_people([
            self.sam_person(common="BR-22-9999 - CENTRAL"),
        ], catalog)
        self.assertEqual(people, [])

    def test_common_without_code_must_resolve_unambiguously(self):
        catalog = [
            {"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"},
            {"comum": "BR-22-0002 - CENTRAL", "cidade": "JANDIRA"},
        ]
        self.assertEqual(admin_views._congregation_people([
            self.sam_person(common="CENTRAL", city=""),
        ], catalog), [])
        people = admin_views._congregation_people([
            self.sam_person(common="CENTRAL", city="JANDIRA"),
        ], catalog)
        self.assertEqual(people[0]["comum"], "BR-22-0002 - CENTRAL")

    @patch.object(admin_views, "common_catalog")
    @patch.object(admin_views, "_get_table")
    def test_multiple_roles_count_one_person_and_ignore_stale_assignments(self, get_table, catalog):
        catalog.return_value = [{"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"}]
        registry = [self.sam_person(role="Encarregado Regional / Encarregado Local")]
        get_table.side_effect = lambda table, params: registry if table == "musica_acompanhamento_aluno" else []
        rows, people = admin_views._congregation_data(include_people=True)
        self.assertEqual(rows[0]["quantidade_servos"], 1)
        self.assertEqual(len(rows[0]["servos"]), 2)
        self.assertEqual(len(people), 2)
        self.assertEqual(len({p["person_key"] for p in people}), 1)

    def test_ministry_is_kept_for_offices_and_sam_is_exclusive_for_music(self):
        catalog = [{"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"}]
        ministry = [
            {"id": "a", "nome": "Anciao", "ministerio": "ANCIAO", "comum": f"{self.code} - CENTRAL"},
            {"id": "b", "nome": "Cargo musical antigo", "ministerio": "Encarregado Regional", "comum": f"{self.code} - CENTRAL"},
        ]
        people = admin_views._congregation_people([
            self.sam_person(role="SECRETARIO (A) DA MUSICA", name="Secretario"),
        ], catalog, ministry)
        self.assertEqual([(p["nome"], p["source"]) for p in people], [
            ("Anciao", "ministerio"), ("Secretario", "sam"),
        ])

    @patch.object(admin_views, "common_catalog")
    @patch.object(admin_views, "_get_table")
    def test_repeated_common_code_does_not_duplicate_rows_or_totals(self, get_table, catalog):
        catalog.return_value = [
            {"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"},
            {"comum": f"{self.code} - CENTRAL OUTRA DESCRICAO", "cidade": "ITAPEVI"},
        ]
        get_table.side_effect = lambda table, params: [self.sam_person()] if table == "musica_acompanhamento_aluno" else []
        rows, people = admin_views._congregation_data(include_people=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(sum(r["quantidade_servos"] for r in rows), len(people))

    @patch.object(admin_views, "_get_table")
    def test_sam_registry_reads_all_pages(self, get_table):
        get_table.side_effect = [[{"id": str(i)} for i in range(1000)], [{"id": "1000"}]]
        self.assertEqual(len(admin_views._sam_congregation_registry()), 1001)
        self.assertEqual(get_table.call_args.kwargs, {})
        self.assertEqual(get_table.call_args.args[1]["offset"], "1000")

    def test_generic_secretary_uses_explicit_organist_data(self):
        catalog = [{"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"}]
        people = admin_views._congregation_people([
            self.sam_person("1", "SECRETÁRIO (A) DA MÚSICA", "Pessoa A (ORGANISTA)"),
            {**self.sam_person("2", "SECRETÁRIO (A) DA MÚSICA", "Pessoa B"), "instrumento": "ÓRGÃO"},
            self.sam_person("3", "SECRETÁRIO (A) DA MÚSICA", "Pessoa C"),
        ], catalog)
        roles = {p["nome"]: p["ministerio"] for p in people}
        self.assertEqual(roles["Pessoa A"], "Secretária da Música")
        self.assertEqual(roles["Pessoa B"], "Secretária da Música")
        self.assertEqual(roles["Pessoa C"], "Secretário da Música")

    def test_organist_annotation_does_not_duplicate_same_secretary(self):
        catalog = [{"comum": f"{self.code} - CENTRAL", "cidade": "ITAPEVI"}]
        people = admin_views._congregation_people([
            self.sam_person("1", "SECRETÁRIO (A) DA MÚSICA", "Pessoa (ORGANISTA)"),
            self.sam_person("2", "SECRETÁRIA DA MÚSICA", "Pessoa"),
        ], catalog)
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["ministerio"], "Secretária da Música")

    def test_person_must_match_exact_congregation_code(self):
        self.assertTrue(admin_views._person_matches_congregation(
            {"comum": f"{self.code} - CENTRAL"},
            f"{self.code} - CENTRAL",
            self.code,
        ))
        self.assertFalse(admin_views._person_matches_congregation(
            {"comum": "BR-21-0798 - CENTRAL II"},
            f"{self.code} - CENTRAL",
            self.code,
        ))

    @patch.object(admin_views, "log_audit")
    @patch.object(admin_views.requests, "post")
    @patch.object(admin_views, "_get_table", return_value=[])
    @patch.object(admin_views, "_fetch_congregation_people", return_value=[{
        "id": "ministerio:regional-1", "categoria": "encarregados_regionais",
        "comum": f"{code} - CENTRAL", "municipio": "SANTANA DE PARNAÍBA",
    }])
    @patch.object(admin_views, "common_catalog", return_value=[{
        "comum": f"{code} - CENTRAL", "cidade": "SANTANA DE PARNAÍBA",
    } for code in ["BR-21-0797"]])
    def test_selected_regional_responsibles_are_saved_as_distribution(self, catalog, people, get_table, post, audit):
        post.return_value = self.response(201, [{
            "congregation_code": self.code,
            "nome": f"{self.code} - CENTRAL",
            "municipio": "SANTANA DE PARNAÍBA",
            "administracao": "",
            "encarregados_regionais": ["ministerio:regional-1"],
            "examinadoras": [],
            "secretarios_musica": [],
            "encarregados_locais": [],
            "secretarios_gem": [],
        }])

        response = admin_views.congregation_record(
            self.request("patch", {"encarregados_regionais": ["ministerio:regional-1"]}),
            self.code,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_args.kwargs["json"]["encarregados_regionais"], ["ministerio:regional-1"])
        audit.assert_called_once()

    @patch.object(admin_views, "log_audit")
    @patch.object(admin_views.requests, "post")
    @patch.object(admin_views, "_get_table", return_value=[])
    @patch.object(admin_views, "common_catalog")
    def test_delete_archives_without_deleting_shared_catalog(self, catalog, get_table, post, audit):
        catalog.return_value = [{"comum": f"{self.code} - CENTRAL", "cidade": "SANTANA DE PARNAÍBA"}]
        post.return_value = self.response(201, [{
            "congregation_code": self.code,
            "nome": f"{self.code} - CENTRAL",
            "municipio": "SANTANA DE PARNAÍBA",
            "administracao": "",
            "archived_at": "2026-11-10T00:00:00+00:00",
        }])

        response = admin_views.congregation_record(self.request("delete"), self.code)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(post.call_args.kwargs["json"]["archived_at"])
        self.assertEqual(get_table.call_count, 1)
        audit.assert_called_once()

    @patch.object(admin_views, "common_catalog")
    def test_non_administrator_cannot_archive_congregation(self, catalog):
        response = admin_views.congregation_record(self.request("delete", role=4), self.code)
        self.assertEqual(response.status_code, 403)
        catalog.assert_not_called()

    @patch.object(admin_views, "common_catalog", return_value=[{
        "comum": f"{code} - CENTRAL", "cidade": "SANTANA DE PARNAÍBA",
    } for code in ["BR-21-0797"]])
    @patch.object(admin_views, "_get_table", return_value=[])
    @patch.object(admin_views, "_fetch_congregation_people", return_value=[{
        "id": "ministerio:examiner-1", "categoria": "examinadoras",
    }])
    @patch.object(admin_views.requests, "post")
    def test_assignment_rejects_people_from_a_different_role(self, post, people, get_table, catalog):
        response = admin_views.congregation_record(
            self.request("patch", {"secretarios_musica": ["ministerio:examiner-1"]}),
            self.code,
        )
        self.assertEqual(response.status_code, 400)
        post.assert_not_called()

    @patch.object(admin_views, "common_catalog", return_value=[{
        "comum": f"{code} - CENTRAL", "cidade": "SANTANA DE PARNAÍBA",
    } for code in ["BR-21-0797"]])
    @patch.object(admin_views, "_get_table", return_value=[])
    @patch.object(admin_views, "_fetch_congregation_people", return_value=[{
        "id": "ministerio:other-common", "categoria": "encarregados_regionais",
        "comum": "BR-21-0798 - CENTRAL II", "municipio": "SANTANA DE PARNAÍBA",
    }])
    @patch.object(admin_views.requests, "post")
    def test_assignment_rejects_people_from_a_different_common(self, post, people, get_table, catalog):
        response = admin_views.congregation_record(
            self.request("patch", {"encarregados_regionais": ["ministerio:other-common"]}),
            self.code,
        )

        self.assertEqual(response.status_code, 400)
        post.assert_not_called()
