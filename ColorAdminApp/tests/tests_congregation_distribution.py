import json
from unittest.mock import patch

import requests
from django.test import RequestFactory, SimpleTestCase

from ColorAdminApp import admin_views
distribution = admin_views.congregation_distribution


class CongregationDistributionTests(SimpleTestCase):
    def test_confirmed_official_distribution_and_multiple_residences(self):
        data = distribution.seed()
        self.assertEqual(data["pending"], [])
        self.assertEqual(data["pdf_commons"], 41)
        self.assertEqual(len(data["assignments"]), len({(a["congregation_code"], a["role"], a["person_id"]) for a in data["assignments"]}))
        edwil = [a for a in data["assignments"] if a["nome"] == "EDWIL SANTOS NETO"]
        self.assertTrue(edwil)
        self.assertTrue(all(set(a["residence_codes"]) == {"BR-22-0673", "BR-21-1039"} for a in edwil))
        for target in ["BR-22-0673", "BR-21-1039"]:
            self.assertEqual(distribution.annotate(edwil[0], target)["relationship"], "residente")
        itaparica = [a for a in data["assignments"] if a["congregation_code"] == "BR-22-3179"]
        for name in ["LUCIANO DO NASCIMENTO", "RICARDO DE CASTRO GRANGEIRO"]:
            item = next(a for a in itaparica if a["nome"] == name)
            self.assertEqual(distribution.annotate(item, "BR-22-3179")["relationship"], "assistencia")
        central = [a for a in data["assignments"] if a["congregation_code"] == "BR-22-1251" and a["role"] == "anciao"]
        self.assertTrue(any(a["nome"] == "SALOMÃO LUIZ DE ALBUQUERQUE" for a in central))
        self.assertFalse(any(a["nome"] == "FLÁVIO LUIZ" for a in central))

    def test_capela_and_alphaville_are_distinct(self):
        catalog = distribution.corrected_catalog([
            {"comum": "BR-21-1251 - ALPHAVILLE"},
            {"comum": "BR-21-1251 - CAPELA VELHA - SURU"},
        ])
        self.assertEqual(catalog[0]["comum"], "BR-21-1251 - ALPHAVILLE")
        self.assertEqual(catalog[1]["comum"], "BR-21-1303 - CAPELA VELHA - SURU")

    def test_pdf_examiners_cover_41_commons_and_izabel_assists_chacara_solar(self):
        examiners = [a for a in distribution.seed()["assignments"] if a["role"] == "examinadora"]
        documented = [a for a in examiners if a["source_document"].endswith(".pdf")]
        self.assertEqual(len(documented), 41)
        self.assertEqual(len({a["congregation_code"] for a in documented}), 41)
        solar = next(a for a in documented if a["congregation_code"] == "BR-21-1564")
        self.assertEqual(solar["nome"], "IZABEL CRISTINA DE FARIAS LINO")
        self.assertEqual(solar["role_label"], "Examinadora de Organista")
        self.assertEqual(distribution.annotate(solar, "BR-21-1564")["relationship"], "assistencia")
        self.assertTrue(all(a["residence_codes"] for a in examiners))
        persons = distribution.directory([])
        self.assertIn("examinadora", persons[solar["person_id"]]["roles"])

    def test_examiner_distribution_replaces_native_entry_without_duplication(self):
        source = {"assignments": [{"congregation_code": "BR-22-0001", "person_id": "sam:1", "nome": "Examinadora",
                                   "role": "examinadora", "residence_codes": ["BR-22-0001"]}], "pending": []}
        person = {"source": "sam", "source_id": "1", "nome": "Examinadora", "ministerio": "EXAMINADORA DE ORGANISTAS",
                  "comum": "BR-22-0001 - COMUM", "categoria": "examinadoras"}
        rows = [{"codigo": "BR-22-0001", "nome": "COMUM", "municipio": "ITAPEVI", "servos": [dict(person)]}]
        with patch.object(distribution, "seed", return_value=source):
            distribution.apply(rows, [person])
        self.assertEqual(len(rows[0]["servos"]), 1)
        self.assertEqual(rows[0]["servos"][0]["categoria"], "examinadoras")
        self.assertEqual(rows[0]["servos"][0]["relationship"], "residente")
        self.assertEqual(rows[0]["missing_assignment_roles"], [])

    def test_complete_cotia_workbook_includes_joint_examiner_assignments(self):
        data = distribution.seed()
        self.assertEqual(data["examiner_workbook_commons"], 65)
        records = [a for a in data["assignments"] if a["role"] == "examinadora"
                   and a["source_document"] == "RELAÇÃO MINISTÉRIO E CARGOS.xlsx"]
        self.assertEqual(len(records), 67)
        grouped = {}
        for record in records:
            grouped.setdefault(record["congregation_code"], []).append(record["nome"])
        self.assertEqual(len(grouped), 65)
        joint = [names for names in grouped.values() if len(names) == 2]
        self.assertEqual(len(joint), 2)
        self.assertTrue(all(set(names) == {"HELENA PINHEIRO RODRIGUES", "MARISTELA MATIAS LIMA"} for names in joint))
        self.assertEqual({a["nome"] for a in records}, {"HELENA PINHEIRO RODRIGUES", "MARISTELA MATIAS LIMA"})

    def test_itapevi_examiner_workbook_covers_all_51_commons(self):
        records = [a for a in distribution.seed()["assignments"]
                   if a["role"] == "examinadora" and a.get("source_sheet") == "Dados"
                   and a.get("source_column") == "F"]
        self.assertEqual(len(records), 51)
        self.assertEqual(len({a["congregation_code"] for a in records}), 51)
        self.assertEqual(sum(a["nome"] == "MAGDA DERTINATI SABINO" for a in records), 26)
        self.assertEqual(sum(a["nome"] == "MIRIAN FRANCISLINE MARIANO DE SOUSA MONTEIRO" for a in records), 25)
        by_common = {a["congregation_code"]: a for a in records}
        self.assertEqual(by_common["BR-21-1039"]["nome"], "MAGDA DERTINATI SABINO")
        self.assertEqual(by_common["BR-22-0679"]["nome"], "MIRIAN FRANCISLINE MARIANO DE SOUSA MONTEIRO")
        self.assertEqual(by_common["BR-21-1481"]["source_row"], 45)
        self.assertEqual(by_common["BR-22-2934"]["nome"], "MAGDA DERTINATI SABINO")
        self.assertEqual(by_common["BR-22-2934"]["residence_codes"], ["BR-21-1039"])

    def test_residence_to_confirm_is_not_assumed(self):
        self.assertEqual(distribution.annotate({"residence_codes": []}, "BR-22-0001")["relationship"], "a_confirmar")

    def test_current_name_overrides_imported_copy_and_removes_role_annotation(self):
        source = {"assignments": [{"congregation_code": "BR-22-0001", "person_id": "sam:1", "nome": "Nome antigo (ORGANISTA)",
                                   "role": "secretario", "residence_codes": ["BR-22-0001"]}], "pending": []}
        person = {"source": "sam", "source_id": "1", "nome": "Nome atualizado (Organista)", "ministerio": "Secretária da Música",
                  "comum": "BR-22-0001 - COMUM", "categoria": "secretarios_musica"}
        rows = [{"codigo": "BR-22-0001", "nome": "COMUM", "municipio": "ITAPEVI", "servos": [dict(person)]}]
        override = {"congregation_code": "BR-22-0001", "assignments": source["assignments"], "revision": 1}
        with patch.object(distribution, "seed", return_value=source):
            people = distribution.apply(rows, [person], [override])
        self.assertEqual(people[0]["nome"], "Nome atualizado")
        self.assertEqual(rows[0]["assignments"][0]["nome"], "Nome atualizado")
        self.assertEqual(rows[0]["servos"][0]["nome"], "Nome atualizado")
        self.assertEqual(rows[0]["servos"][0]["ministerio"], "Secretária da Música")
        self.assertEqual(override["assignments"][0]["nome"], "Nome antigo (ORGANISTA)")

    def test_four_administrations_follow_the_user_defined_groups(self):
        for cities in [
            ["Cotia", "Caucaia do Alto", "Vargem Grande Paulista"],
            ["Santana de Parnaíba", "Pirapora do Bom Jesus"],
        ]:
            self.assertEqual(len({distribution.administration(c) for c in cities}), 1)
        self.assertEqual(len({distribution.administration(c) for c in ["Cotia", "Jandira", "Itapevi", "Santana de Parnaíba"]}), 4)

    def test_selection_and_residences_cannot_cross_administrations(self):
        catalog = [
            {"comum": "BR-22-0001 - COMUM A", "cidade": "COTIA"},
            {"comum": "BR-22-0002 - COMUM B", "cidade": "VARGEM GRANDE PAULISTA"},
            {"comum": "BR-22-0003 - COMUM C", "cidade": "ITAPEVI"},
        ]
        people = {"ministerio:1": {"nome": "Ancião de Cotia", "roles": ["anciao"], "residence_codes": ["BR-22-0001"]}}
        scoped = distribution.scoped_directory(people, catalog)
        self.assertEqual(scoped["ministerio:1"]["administration_ids"], ["cotia_caucaia_vgp"])
        item = {"role": "anciao", "person_id": "ministerio:1", "residence_codes": ["BR-22-0001"]}
        self.assertEqual(len(distribution.validate_assignments([item], people, catalog, "BR-22-0002")), 1)
        with self.assertRaisesMessage(ValueError, "outra administração"):
            distribution.validate_assignments([item], people, catalog, "BR-22-0003")
        with self.assertRaisesMessage(ValueError, "residências dentro"):
            distribution.validate_assignments([{**item, "residence_codes": ["BR-22-0003"]}], people, catalog, "BR-22-0001")

    def test_person_with_multiple_residences_retains_each_administration(self):
        catalog = [{"comum": "BR-22-0001 - A", "cidade": "ITAPEVI"}, {"comum": "BR-22-0002 - B", "cidade": "JANDIRA"}]
        person = {"x": {"residence_codes": ["BR-22-0001", "BR-22-0002"]}}
        self.assertEqual(distribution.scoped_directory(person, catalog)["x"]["administration_ids"], ["itapevi", "jandira"])

    def test_local_leaders_follow_corrected_capela_code_without_mixing_alphaville(self):
        catalog = [
            {"comum": "BR-21-1251 - ALPHAVILLE", "cidade": "SANTANA DE PARNAÍBA"},
            {"comum": "BR-21-1303 - CAPELA VELHA - SURU", "cidade": "SANTANA DE PARNAÍBA"},
        ]
        sam = [
            {"id": "patrick", "nome_aluno": "PATRICK SANTOS DO NASCIMENTO", "cargo_ministerio": "ENCARREGADO LOCAL", "comum_congregacao": "BR-21-1251 - CAPELA VELHA - SURU"},
            {"id": "marcio", "nome_aluno": "MARCIO LINO", "cargo_ministerio": "ENCARREGADO LOCAL", "comum_congregacao": "BR-21-1251 - ALPHAVILLE"},
        ]
        people = admin_views._congregation_people(sam, catalog)
        codes = {p["nome"]: distribution.common_code(p["comum"]) for p in people}
        self.assertEqual(codes["PATRICK SANTOS DO NASCIMENTO"], "BR-21-1303")
        self.assertEqual(codes["MARCIO LINO"], "BR-21-1251")
        self.assertEqual(sam[0]["comum_congregacao"], "BR-21-1251 - CAPELA VELHA - SURU")

    def test_validation_rejects_unknown_people_and_duplicate_roles(self):
        persons = {"sam:1": {"nome": "Pessoa", "residence_codes": [], "roles": ["regional"]}}
        catalog = [{"comum": "BR-22-0001 - COMUM"}]
        with self.assertRaises(ValueError):
            distribution.validate_assignments([{"person_id": "sam:missing", "role": "anciao"}], persons, catalog)
        item = {"person_id": "sam:1", "role": "regional", "residence_codes": ["BR-22-0001"]}
        with self.assertRaises(ValueError):
            distribution.validate_assignments([item, item], persons, catalog)
        result = distribution.validate_assignments([item], persons, catalog)
        self.assertEqual(result[0]["nome"], "Pessoa")

    def test_empty_override_replaces_defaults_instead_of_restoring_them(self):
        source = {"assignments": [{"congregation_code": "BR-22-0001", "person_id": "sam:1", "nome": "Pessoa",
                                   "role": "regional", "residence_codes": ["BR-22-0002"]}], "pending": []}
        rows = [{"codigo": "BR-22-0001", "nome": "COMUM", "municipio": "CIDADE", "servos": []}]
        with patch.object(distribution, "seed", return_value=source):
            distribution.apply(rows, [], [{"congregation_code": "BR-22-0001", "assignments": [], "revision": 2}])
        self.assertEqual(rows[0]["servos"], [])
        self.assertEqual(rows[0]["assignment_revision"], 2)

    def test_outdated_residence_from_another_common_is_rejected(self):
        persons = {"sam:1": {"nome": "Pessoa", "roles": ["regional"], "residence_codes": ["BR-22-0002"]}}
        catalog = [{"comum": "BR-22-0001 - COMUM A"}, {"comum": "BR-22-0002 - COMUM B"}]
        with self.assertRaises(distribution.ResidenceConflict):
            distribution.validate_assignments([{
                "person_id": "sam:1", "role": "regional", "residence_codes": ["BR-22-0001"],
                "expected_residence_codes": ["BR-22-0001"],
            }], persons, catalog)

    def test_missing_table_only_disables_editing(self):
        response = requests.Response()
        response.status_code = 404
        with patch.object(admin_views, "_get_table", side_effect=requests.HTTPError(response=response)):
            self.assertEqual(distribution.load_overrides(admin_views._get_table), ([], False))


class DistributionMutationTests(SimpleTestCase):
    code = "BR-22-0001"

    def request(self, body, role=1):
        req = RequestFactory().patch(f"/administracao/api/operacional/congregacoes/{self.code}/assistencias/",
                                     data=json.dumps(body), content_type="application/json")
        req.session = {"user_id": "actor", "user_profile": {"role_id": role}}
        return req

    def test_local_user_cannot_change_distribution(self):
        self.assertEqual(admin_views.congregation_distribution_record(self.request({}, 4), self.code).status_code, 403)

    @patch.object(admin_views, "common_catalog", return_value=[{"comum": "BR-22-0001 - COMUM", "cidade": "ITAPEVI"}])
    @patch.object(distribution, "load_overrides", return_value=([{"congregation_code": "BR-22-0001", "revision": 2, "assignments": []}], True))
    @patch.object(admin_views, "_fetch_congregation_people", return_value=[])
    @patch.object(admin_views.requests, "patch")
    def test_stale_revision_does_not_overwrite_newer_distribution(self, write, people, overrides, catalog):
        result = admin_views.congregation_distribution_record(self.request({"revision": 1, "assignments": []}), self.code)
        self.assertEqual(result.status_code, 409)
        write.assert_not_called()

    @patch.object(admin_views, "common_catalog", return_value=[{"comum": "BR-22-0001 - COMUM", "cidade": "ITAPEVI"}])
    @patch.object(distribution, "load_overrides", return_value=([], True))
    @patch.object(admin_views, "_fetch_congregation_people", return_value=[])
    @patch.object(admin_views.requests, "post")
    @patch.object(admin_views, "log_audit")
    def test_save_does_not_update_official_residence_tables(self, audit, write, people, overrides, catalog):
        response = requests.Response()
        response.status_code = 201
        response._content = json.dumps([{"congregation_code": self.code, "assignments": [], "revision": 1}]).encode()
        write.return_value = response
        result = admin_views.congregation_distribution_record(self.request({"revision": 0, "assignments": []}), self.code)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(write.call_args.args[0].endswith("/" + distribution.TABLE))
        audit.assert_called_once()
