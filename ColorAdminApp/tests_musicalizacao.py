import json
from datetime import date
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from .musicalizacao import RESOURCES, REGIONAL_MUNICIPALITIES, _child_age, _child_age_error, _child_polo_city, _normalize_birth_date, _set_polo_coordinator, _visible, api_resource, api_summary, can_open_module


def request_with_profile(path, profile, method="get", data=None):
    factory = RequestFactory()
    if method == "get":
        request = factory.get(path)
    else:
        request = getattr(factory, method)(path, data=json.dumps(data or {}), content_type="application/json")
    request.session = {"authenticated": True, "user_profile": profile}
    return request


@override_settings(SUPABASE_URL="https://db.example", SUPABASE_SERVICE_ROLE_KEY="secret")
class MusicalizacaoSecurityTests(SimpleTestCase):
    def test_child_age_uses_completed_years(self):
        self.assertEqual(_child_age("20/09/2019", today=date(2026, 8, 26)), 6)
        self.assertEqual(_child_age("2019-08-20", today=date(2026, 8, 26)), 7)
        self.assertEqual(_child_age("14122020", today=date(2026, 8, 26)), 5)

    def test_normalize_birth_date_formats(self):
        self.assertEqual(_normalize_birth_date("14122022"), "2022-12-14")
        self.assertEqual(_normalize_birth_date("14/12/2022"), "2022-12-14")
        self.assertEqual(_normalize_birth_date("2022-12-14"), "2022-12-14")
        self.assertEqual(_normalize_birth_date(""), None)

    def test_child_age_range_routes_ten_year_old_to_gem(self):
        today = date.today()
        nine_year_old = date(today.year - 9, today.month, today.day).isoformat()
        ten_year_old = date(today.year - 10, today.month, today.day).isoformat()
        self.assertIsNone(_child_age_error(nine_year_old))
        self.assertIn("GEM", _child_age_error(ten_year_old))

    @patch("ColorAdminApp.musicalizacao.common_catalog")
    def test_child_management_city_comes_from_polo_not_home_address(self, catalog):
        catalog.return_value = [{"comum": "BR-22-0673 - VILA DOUTOR CARDOSO", "cidade": "ITAPEVI"}]
        child = {
            "cidade": "JANDIRA",
            "comum_congregacao": "BR-22-0673 - VILA DOUTOR CARDOSO",
            "polo_participacao": "BR-22-0673 - VILA DOUTOR CARDOSO",
        }
        self.assertEqual(_child_polo_city(child), "ITAPEVI")

    @patch("ColorAdminApp.musicalizacao.common_catalog")
    def test_local_instructor_scope_uses_assigned_polo(self, catalog):
        catalog.return_value = [
            {"comum": "POLO CENTRAL", "cidade": "ITAPEVI"},
            {"comum": "POLO JARDIM", "cidade": "ITAPEVI"},
        ]
        scope = {"level": "local", "comum": "POLO CENTRAL", "municipio": "ITAPEVI", "profile": {}}
        rows = [
            {"nome_completo": "Ana", "comum_congregacao": "OUTRA COMUM", "polo_auxilio": "POLO CENTRAL"},
            {"nome_completo": "Bia", "comum_congregacao": "POLO CENTRAL", "polo_auxilio": "POLO JARDIM"},
        ]
        self.assertEqual([row["nome_completo"] for row in _visible(scope, RESOURCES["instrutores"], rows)], ["Ana"])

    def test_regional_catalog_keeps_all_seven_municipalities(self):
        self.assertEqual(REGIONAL_MUNICIPALITIES, [
            "CAUCAIA DO ALTO", "COTIA", "ITAPEVI", "JANDIRA",
            "PIRAPORA DO BOM JESUS", "SANTANA DE PARNAIBA", "VARGEM GRANDE PAULISTA",
        ])

    @patch("ColorAdminApp.musicalizacao.requests.patch")
    @patch("ColorAdminApp.musicalizacao._coordinator_rows")
    def test_assigning_polo_coordinator_updates_single_source_of_truth(self, coordinator_rows, mock_patch):
        coordinator_rows.return_value = [
            {"id": "old", "nome_completo": "Coordenadora anterior", "role": "Coordenadora", "polo_auxilio": "POLO CENTRAL"},
            {"id": "new", "nome_completo": "Nova coordenadora", "role": "Instrutora", "polo_auxilio": "POLO JARDIM", "comum_congregacao": "POLO CENTRAL"},
        ]
        mock_patch.return_value.raise_for_status.return_value = None

        _set_polo_coordinator({"level": "global", "municipio": "", "comum": "", "profile": {}}, "POLO CENTRAL", "new")

        self.assertEqual(mock_patch.call_count, 2)
        self.assertEqual(mock_patch.call_args_list[0].kwargs["json"], {"polo_auxilio": None})
        self.assertEqual(mock_patch.call_args_list[1].kwargs["json"], {"polo_auxilio": "POLO CENTRAL", "role": "Coordenadora"})

    def test_visitas_coordinator_cannot_open_musicalizacao(self):
        request = request_with_profile("/musicalizacao/", {"role_id": 2, "sector": "Visitas"})
        self.assertFalse(can_open_module(request))
        self.assertEqual(api_summary(request).status_code, 403)

    def test_musicalizacao_coordinator_can_open_own_folder(self):
        request = request_with_profile("/musicalizacao/", {"role_id": 2, "sector": "Musicalização"})
        self.assertTrue(can_open_module(request))

    @patch("ColorAdminApp.musicalizacao.requests.get")
    def test_local_profile_only_receives_records_from_own_common(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [
            {"id": "1", "nome_crianca": "Ana", "comum_congregacao": "BR-01 - CENTRAL ITAPEVI", "cidade": "ITAPEVI"},
            {"id": "2", "nome_crianca": "Bia", "comum_congregacao": "BR-02 - JARDIM JANDIRA", "cidade": "JANDIRA"},
        ]
        mock_get.return_value = response
        profile = {"role_id": 4, "sector": "Musicalização", "access_level": "local", "comum": "BR-01 - CENTRAL ITAPEVI"}
        request = request_with_profile("/musicalizacao/api/criancas/", profile)

        with patch("ColorAdminApp.access_control.common_catalog", return_value=[]):
            result = api_resource(request, "criancas")

        body = json.loads(result.content)
        self.assertEqual([item["id"] for item in body["items"]], ["1"])

    def test_payload_cannot_assign_record_outside_local_scope(self):
        profile = {"role_id": 4, "sector": "Musicalização", "access_level": "local", "comum": "BR-01 - CENTRAL ITAPEVI"}
        request = request_with_profile("/musicalizacao/api/criancas/", profile, "post", {
            "nome_crianca": "Bia", "comum_congregacao": "BR-02 - JARDIM JANDIRA", "cidade": "JANDIRA"
        })

        with patch("ColorAdminApp.access_control.common_catalog", return_value=[]):
            result = api_resource(request, "criancas")

        self.assertEqual(result.status_code, 403)
