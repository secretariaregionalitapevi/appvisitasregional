from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .module_access import MODULE_MUSICALIZACAO, MODULE_VISITAS, allowed_modules, can_access_module


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
        self.assertEqual(allowed_modules(request), {MODULE_MUSICALIZACAO, MODULE_VISITAS})
