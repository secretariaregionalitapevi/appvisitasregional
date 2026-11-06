from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from ColorAdminApp.module_access import MODULE_MUSICA, MODULE_DARPE, MODULE_MUSICALIZACAO, MODULE_VISITAS, allowed_modules, can_access_module


def request_for(profile, user_id="00000000-0000-0000-0000-000000000001"):
    request = RequestFactory().get("/")
    request.session = {"user_profile": profile, "user_id": user_id}
    return request


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
        self.assertEqual(allowed_modules(request), {MODULE_MUSICA, MODULE_DARPE, MODULE_MUSICALIZACAO, MODULE_VISITAS})

    def test_administrativo_sector_keeps_both_folders(self):
        request = request_for({"role_id": 2, "sector": "Administrativo", "access_level": "regional"})
        self.assertEqual(allowed_modules(request), {MODULE_MUSICA, MODULE_DARPE, MODULE_MUSICALIZACAO, MODULE_VISITAS})

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
