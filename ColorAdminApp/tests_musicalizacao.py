import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from .musicalizacao import REGIONAL_MUNICIPALITIES, _child_polo_city, api_resource, api_summary, can_open_module


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
    @patch("ColorAdminApp.musicalizacao.common_catalog")
    def test_child_management_city_comes_from_polo_not_home_address(self, catalog):
        catalog.return_value = [{"comum": "BR-22-0673 - VILA DOUTOR CARDOSO", "cidade": "ITAPEVI"}]
        child = {
            "cidade": "JANDIRA",
            "comum_congregacao": "BR-22-0673 - VILA DOUTOR CARDOSO",
            "polo_participacao": "BR-22-0673 - VILA DOUTOR CARDOSO",
        }
        self.assertEqual(_child_polo_city(child), "ITAPEVI")

    def test_regional_catalog_keeps_all_seven_municipalities(self):
        self.assertEqual(REGIONAL_MUNICIPALITIES, [
            "CAUCAIA DO ALTO", "COTIA", "ITAPEVI", "JANDIRA",
            "PIRAPORA DO BOM JESUS", "SANTANA DE PARNAIBA", "VARGEM GRANDE PAULISTA",
        ])

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
