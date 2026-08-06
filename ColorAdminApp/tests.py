from unittest.mock import Mock, patch

from django.test import RequestFactory, TestCase

from .access_control import can_access, filter_rows, user_scope
from .admin_views import administration, administration_data
from .views import apiRoteiroBairros, apiVisitasEquipes, apiVisitasIrmandade

CATALOG = [
    {"comum": "BR-01 - CENTRAL ITAPEVI", "cidade": "ITAPEVI"},
    {"comum": "BR-02 - JARDIM JANDIRA", "cidade": "JANDIRA"},
    {"comum": "BR-03 - ALTO ITAPEVI", "cidade": "ITAPEVI"},
]


class RegionalAccessTests(TestCase):
    def request_with_profile(self, profile):
        request = RequestFactory().get("/")
        request.session = {"user_profile": profile}
        return request

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_local_user_only_sees_own_common(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 4, "comum": CATALOG[0]["comum"]}))
        self.assertTrue(can_access(scope, CATALOG[0]))
        self.assertFalse(can_access(scope, CATALOG[2]))

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_municipal_coordinator_sees_only_municipality(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 3, "comum": CATALOG[0]["comum"]}))
        self.assertEqual(len(filter_rows(scope, CATALOG)), 2)
        self.assertFalse(can_access(scope, CATALOG[1]))

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_regional_coordinator_sees_everything(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 2, "comum": CATALOG[0]["comum"]}))
        self.assertEqual(filter_rows(scope, CATALOG), CATALOG)

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_global_level_has_full_scope(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 1, "comum": CATALOG[0]["comum"]}))
        self.assertEqual(scope["level"], "global")
        self.assertEqual(filter_rows(scope, CATALOG), CATALOG)


class GlobalAdministrationTests(TestCase):
    def request_with_profile(self, role_id, path="/administracao/"):
        request = RequestFactory().get(path)
        request.session = {"user_profile": {"role_id": role_id}}
        return request

    def test_non_global_user_is_redirected_from_admin_page(self):
        response = administration(self.request_with_profile(2))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/v3")

    def test_non_global_user_is_forbidden_from_admin_api(self):
        response = administration_data(self.request_with_profile(3, "/administracao/api/dados/"))
        self.assertEqual(response.status_code, 403)

    @patch("ColorAdminApp.admin_views._get_table", return_value=[])
    def test_global_user_can_consult_admin_api(self, _get_table):
        response = administration_data(self.request_with_profile(1, "/administracao/api/dados/"))
        self.assertEqual(response.status_code, 200)


class IntelligentRouteTests(TestCase):
    def request(self, comum):
        request = RequestFactory().get("/visitas/api/roteiro-bairros/", {"comum": comum, "data": "2026-08-05"})
        request.session = {"user_profile": {"role_id": 4, "comum": comum}}
        return request

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    @patch("ColorAdminApp.utils.routing.discover_nearby_neighborhoods", return_value=[{"nome": "Centro", "quantidade": 3, "distancia_metros": 450}])
    def test_neighborhoods_are_returned_for_common_in_scope(self, _discover, _commons):
        response = apiRoteiroBairros(self.request("COMUM A"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Centro")

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    def test_neighborhoods_reject_common_outside_scope(self, _commons):
        response = apiRoteiroBairros(self.request("COMUM B"))
        self.assertEqual(response.status_code, 403)


class VisitTeamsTests(TestCase):
    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    @patch("ColorAdminApp.views.requests.get")
    def test_members_mode_includes_people_without_team(self, get, _commons):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{
            "id": "1", "nome": "Rodrigo", "comum": "COMUM A",
            "status": "Ativo", "equipe_visita": None, "cargo_outros": "Grupo de Visitas",
        }]
        request = RequestFactory().get("/visitas/api/equipes/?modo=membros&busca=Rodrigo")
        request.session = {"user_profile": {"role_id": 4, "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = apiVisitasEquipes(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rodrigo")

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    def test_existing_member_is_assigned_to_team(self, get, patch_request, _audit):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{"id": "1", "nome": "Ricardo", "comum": "COMUM A", "cidade": "ITAPEVI", "cargo_outros": "Grupo de Visitas"}]
        patch_request.return_value = Mock(status_code=200)
        patch_request.return_value.json.return_value = [{"id": "1", "equipe_visita": "Equipe 01"}]
        request = RequestFactory().post(
            "/visitas/api/equipes/",
            data={"membro_id": "1", "equipe": "Equipe 01"},
            content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 4, "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = apiVisitasEquipes(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(patch_request.call_args.kwargs["json"], {"equipe_visita": "Equipe 01"})


class BrotherhoodUpdateTests(TestCase):
    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    def test_patch_defines_endpoint_before_reading_current_record(self, get, patch_request, _audit):
        current = {"id": "member-1", "nome": "Maria", "comum": "COMUM A", "cidade": "ITAPEVI"}
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [current]
        patch_request.return_value = Mock(status_code=200, text='')
        request = RequestFactory().patch(
            "/visitas/api/irmandade/?id=member-1",
            data={"nome": "Maria Atualizada"}, content_type="application/json",
        )
        request.session = {"user_profile": {"role_id": 4, "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = apiVisitasIrmandade(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/rest/v1/visitas_irmandade", get.call_args.args[0])
