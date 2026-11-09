from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from requests import Timeout

from ColorAdminApp.module_access import MODULE_GEM, MODULE_MUSICA, MODULE_DARPE, MODULE_MUSICALIZACAO, MODULE_VISITAS, allowed_modules, can_access_module


def request_for(profile, user_id="00000000-0000-0000-0000-000000000001"):
    request = RequestFactory().get("/")
    request.session = {"user_profile": profile, "user_id": user_id}
    return request


class TestSession(dict):
    def flush(self):
        self.clear()


class ModuleAccessTests(SimpleTestCase):
    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    def test_regional_visitas_does_not_inherit_musicalizacao(self, _explicit):
        request = request_for({"role_id": 2, "sector": "Visitas", "access_level": "regional"})
        self.assertTrue(can_access_module(request, MODULE_VISITAS))
        self.assertFalse(can_access_module(request, MODULE_MUSICALIZACAO))

    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    def test_regional_musicalizacao_does_not_inherit_visitas(self, _explicit):
        request = request_for({"role_id": 2, "sector": "Musicalização", "access_level": "regional"})
        self.assertEqual(allowed_modules(request), {MODULE_MUSICALIZACAO})

    @patch("ColorAdminApp.module_access.explicit_modules", return_value={MODULE_VISITAS})
    def test_explicit_global_grant_adds_second_folder(self, _explicit):
        request = request_for({"role_id": 2, "sector": "Musicalização", "access_level": "regional"})
        self.assertEqual(allowed_modules(request), {MODULE_MUSICALIZACAO, MODULE_VISITAS})

    def test_master_keeps_both_folders(self):
        request = request_for({"role_id": 1, "sector": "Global"})
        self.assertEqual(allowed_modules(request), {MODULE_MUSICA, MODULE_DARPE, MODULE_MUSICALIZACAO, MODULE_VISITAS, MODULE_GEM})

    def test_administrativo_sector_keeps_both_folders(self):
        request = request_for({"role_id": 2, "sector": "Administrativo", "access_level": "regional"})
        self.assertEqual(allowed_modules(request), {MODULE_MUSICA, MODULE_DARPE, MODULE_MUSICALIZACAO, MODULE_VISITAS, MODULE_GEM})

    def test_ebi_sector_gets_musicalizacao(self):
        request = request_for({"role_id": 4, "sector": "Ebi", "access_level": "local"})
        self.assertEqual(allowed_modules(request), {MODULE_MUSICALIZACAO})

    def test_fallback_when_sector_is_unrecognized(self):
        request = request_for({"role_id": 4, "sector": None, "access_level": "local"})
        self.assertEqual(allowed_modules(request), {MODULE_VISITAS})

    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    def test_municipal_music_is_independent(self, _explicit):
        request = request_for({"role_id": 3, "sector": "Música", "access_level": "municipal"})
        self.assertEqual(allowed_modules(request), {MODULE_MUSICA})

    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    def test_gem_sector_is_independent_from_musicalizacao(self, _explicit):
        request = request_for({"role_id": 4, "sector": "G.E.M", "access_level": "local"})
        self.assertEqual(allowed_modules(request), {MODULE_GEM})
        self.assertTrue(can_access_module(request, MODULE_GEM))
        self.assertFalse(can_access_module(request, MODULE_MUSICALIZACAO))


class MusicOnlyDashboardTests(SimpleTestCase):
    @patch("ColorAdminApp.middleware.requests.get")
    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    def test_music_only_cannot_enter_main_dashboard_api(self, _modules, get):
        from ColorAdminApp.middleware import SupabaseAuthMiddleware
        from django.http import HttpResponse
        profile = {"user_id": "test", "status": "approved", "role_id": 3, "sector": "M\u00fasica", "municipio": "Itapevi"}
        get.return_value.status_code = 200
        get.return_value.json.return_value = [profile]
        request = RequestFactory().get("/api/dashboard/")
        request.session = {"authenticated": True, "user_id": "test", "user_profile": profile}
        response = SupabaseAuthMiddleware(lambda req: HttpResponse("private dashboard"))(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"cartas_app_only", response.content)

    @patch("ColorAdminApp.middleware.requests.get")
    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    def test_music_only_redirects_to_cartas_admin(self, _modules, get):
        from ColorAdminApp.middleware import SupabaseAuthMiddleware
        from django.http import HttpResponse
        from django.test import override_settings
        profile = {"user_id": "test", "status": "approved", "role_id": 3, "sector": "M\u00fasica", "municipio": "Itapevi"}
        get.return_value.status_code = 200
        get.return_value.json.return_value = [profile]
        request = RequestFactory().get("/")
        request.session = {"authenticated": True, "user_id": "test", "user_profile": profile}
        with override_settings(CARTAS_APP_URL="https://cartas.example.test"):
            response = SupabaseAuthMiddleware(lambda req: HttpResponse("private dashboard"))(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://cartas.example.test/admin")


class DepartmentAccessMiddlewareTests(SimpleTestCase):
    sectors = {
        "Visitas": (MODULE_VISITAS, "/visitas/api/dashboard/"),
        "Musicalização": (MODULE_MUSICALIZACAO, "/musicalizacao/api/resumo/"),
        "D.A.R.P.E": (MODULE_DARPE, "/darpe/api/cadastros/"),
        "G.E.M": (MODULE_GEM, "/gem/api/resumo/"),
        "Música": (MODULE_MUSICA, "/musica/eventos/api/painel/"),
    }

    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    @patch("ColorAdminApp.middleware.requests.get")
    def test_pending_accounts_are_blocked_from_every_department(self, get, _modules):
        from django.http import HttpResponse
        from ColorAdminApp.middleware import SupabaseAuthMiddleware

        get.return_value.status_code = 200
        get.return_value.json.return_value = [{
            "user_id": "pending-user", "status": "pending", "role_id": 4,
            "sector": "Musicalização",
        }]
        middleware = SupabaseAuthMiddleware(lambda _request: HttpResponse("private data"))

        for _sector, (_module, path) in self.sectors.items():
            request = RequestFactory().get(path)
            request.session = TestSession({
                "authenticated": True, "user_id": "pending-user",
                "user_profile": {"role_id": 4, "sector": _sector},
            })
            response = middleware(request)
            self.assertEqual(response.status_code, 401, path)
            self.assertNotIn(b"private data", response.content)

    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    @patch("ColorAdminApp.middleware.requests.get")
    def test_approved_user_cannot_open_another_department_api(self, get, _modules):
        from django.http import HttpResponse
        from ColorAdminApp.middleware import SupabaseAuthMiddleware

        get.return_value.status_code = 200
        get.return_value.json.side_effect = lambda: [{
            "user_id": "approved-user", "status": "approved", "role_id": 4,
            "sector": current_sector,
        }]
        middleware = SupabaseAuthMiddleware(lambda _request: HttpResponse("private data"))

        for sector, (primary_module, _own_path) in self.sectors.items():
            for other_sector, (requested_module, path) in self.sectors.items():
                if requested_module == primary_module:
                    continue
                current_sector = sector
                request = RequestFactory().get(path)
                request.session = TestSession({
                    "authenticated": True, "user_id": "approved-user",
                    "user_profile": {"role_id": 4, "sector": sector},
                })
                response = middleware(request)
                self.assertEqual(response.status_code, 403, f"{sector} -> {other_sector}")
                self.assertNotIn(b"private data", response.content)

    @patch("ColorAdminApp.middleware.requests.get", side_effect=Timeout)
    def test_profile_verification_failure_fails_closed(self, _get):
        from ColorAdminApp.middleware import SupabaseAuthMiddleware

        request = RequestFactory().get("/visitas/api/dashboard/")
        request.session = TestSession({
            "authenticated": True, "user_id": "approved-user",
            "user_profile": {"role_id": 4, "sector": "Visitas", "status": "approved"},
        })
        response = SupabaseAuthMiddleware(lambda _request: self.fail("protected view executed"))(request)
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"approval_check_unavailable", response.content)

    @patch("ColorAdminApp.module_access.explicit_modules", return_value=set())
    @patch("ColorAdminApp.middleware.requests.get")
    def test_dashboard_sends_users_to_their_approved_primary_department(self, get, _modules):
        from django.http import HttpResponse
        from ColorAdminApp.middleware import SupabaseAuthMiddleware

        get.return_value.status_code = 200
        middleware = SupabaseAuthMiddleware(lambda _request: HttpResponse("visitas dashboard"))
        for sector, expected_path in (
            ("Musicalização", "/musicalizacao/"),
            ("G.E.M", "/gem/"),
            ("D.A.R.P.E", "/darpe/"),
        ):
            get.return_value.json.return_value = [{
                "user_id": "approved-user", "status": "approved", "role_id": 4,
                "sector": sector,
            }]
            request = RequestFactory().get("/")
            request.session = TestSession({
                "authenticated": True, "user_id": "approved-user",
                "user_profile": {"role_id": 4, "sector": sector},
            })
            response = middleware(request)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, expected_path)
