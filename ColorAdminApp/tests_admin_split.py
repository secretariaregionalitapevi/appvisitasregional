import json
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from . import admin_views
from .views import _sanitize_audit_value


class AdministrativeSplitTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, path, role_id):
        request = self.factory.get(path)
        request.session = {
            "authenticated": True,
            "user_id": "00000000-0000-0000-0000-000000000001",
            "user_profile": {"role_id": role_id, "role": {1: "Master", 2: "Admin", 4: "Local"}.get(role_id)},
        }
        return request

    @patch("ColorAdminApp.admin_views.render", return_value=HttpResponse("ok"))
    def test_only_global_can_open_audit_center(self, render_mock):
        self.assertEqual(admin_views.audit_center(self.request("/auditoria/", 1)).status_code, 200)
        self.assertEqual(admin_views.audit_center(self.request("/auditoria/", 2)).status_code, 302)
        render_mock.assert_called_once()

    @patch("ColorAdminApp.admin_views.render", return_value=HttpResponse("ok"))
    def test_global_and_regional_admin_can_open_operational_folder(self, render_mock):
        self.assertEqual(admin_views.operational_page(self.request("/administracao/ministerio/", 1), "ministerio").status_code, 200)
        self.assertEqual(admin_views.operational_page(self.request("/administracao/ministerio/", 2), "ministerio").status_code, 200)
        self.assertEqual(admin_views.operational_page(self.request("/administracao/ministerio/", 4), "ministerio").status_code, 302)
        self.assertEqual(render_mock.call_count, 2)

    @patch("ColorAdminApp.admin_views._get_table")
    def test_pending_count_deduplicates_profiles(self, get_table):
        get_table.return_value = [{"user_id": "a"}, {"user_id": "a"}, {"user_id": "b"}, {"user_id": None}]
        response = admin_views.pending_access_count(self.request("/administracao/api/acessos-pendentes/", 1))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["pending_count"], 2)

    @patch("ColorAdminApp.admin_views.common_catalog")
    @patch("ColorAdminApp.admin_views._get_table")
    def test_congregations_are_linked_to_ministry_by_br_code(self, get_table, common_catalog):
        common_catalog.return_value = [{"comum": "BR-21-0797 - JABOTICABEIRA", "cidade": "SANTANA DE PARNAIBA"}]
        get_table.return_value = [
            {"id": "1", "comum": "BR-21-0797 - SANTANA DE PARNAIBA - JABOTICABEIRA", "nome": "Servo 1", "administracao": "ITAPEVI"},
            {"id": "2", "comum": "BR-21-0797 - SANTANA DE PARNAIBA - JABOTICABEIRA", "nome": "Servo 2", "administracao": "ITAPEVI"},
        ]
        rows = admin_views._congregation_rows()
        self.assertEqual(rows[0]["codigo"], "BR-21-0797")
        self.assertEqual(rows[0]["nome_comum"], "JABOTICABEIRA")
        self.assertEqual(rows[0]["quantidade_servos"], 2)

    @patch("ColorAdminApp.admin_views.log_audit")
    @patch("ColorAdminApp.admin_views._congregation_rows")
    def test_excel_export_uses_institutional_standard(self, congregation_rows, log_mock):
        from io import BytesIO
        from openpyxl import load_workbook
        congregation_rows.return_value = [{
            "codigo": "BR-22-1234", "nome": "BR-22-1234 - COMUM TESTE", "nome_comum": "COMUM TESTE",
            "municipio": "ITAPEVI", "administracao": "REGIONAL", "quantidade_servos": 3,
        }]
        request = self.request("/administracao/api/operacional/congregacoes/exportar-excel/", 1)
        response = admin_views.export_congregations_excel(request)
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook["CONGREGACOES"]
        self.assertEqual(sheet["A1"].value, "CONGREGA\u00c7\u00c3O CRIST\u00c3 NO BRASIL")
        self.assertEqual(sheet["A2"].value, "Regional Itapevi - S\u00e3o Paulo")
        self.assertEqual(sheet.freeze_panes, "A7")
        self.assertEqual(sheet.page_setup.orientation, "landscape")
        self.assertEqual(sheet.page_setup.fitToWidth, 1)
        self.assertEqual(sheet["A7"].value, "BR-22-1234")
        self.assertEqual(sheet["B7"].value, "COMUM TESTE")
        self.assertFalse(sheet.sheet_view.showGridLines)
        log_mock.assert_called_once()

    @patch("ColorAdminApp.admin_views.requests.post")
    def test_profile_update_uses_service_role_rpc(self, post_mock):
        post_mock.return_value.status_code = 200
        post_mock.return_value.json.return_value = {
            "user_id": "00000000-0000-0000-0000-000000000099",
            "sector": "Visitas",
        }
        updated = admin_views._update_profile_via_rpc(
            "00000000-0000-0000-0000-000000000099", {"sector": "Visitas"}
        )
        self.assertEqual(updated["sector"], "Visitas")
        self.assertTrue(post_mock.call_args.args[0].endswith("/rest/v1/rpc/admin_update_user_profile"))
        self.assertEqual(post_mock.call_args.kwargs["json"]["p_changes"], {"sector": "Visitas"})
        post_mock.return_value.raise_for_status.assert_called_once()

    def test_admin_profile_rpc_is_restricted_to_service_role(self):
        migration = (
            __import__("pathlib").Path(__file__).resolve().parent.parent
            / "scripts" / "migrations" / "020_secure_admin_profile_update_rpc.sql"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("security definer", migration.lower())
        self.assertIn("to service_role", migration.lower())
        self.assertIn("from public, anon, authenticated", migration.lower())
        self.assertNotIn("grant update on table public.profiles", migration.lower())
    def test_audit_sanitizer_redacts_secrets_recursively(self):
        clean = _sanitize_audit_value({"password": "123", "nested": {"access_token": "secret", "name": "Teste"}})
        self.assertEqual(clean["password"], "[REMOVIDO]")
        self.assertEqual(clean["nested"]["access_token"], "[REMOVIDO]")
        self.assertEqual(clean["nested"]["name"], "Teste")
