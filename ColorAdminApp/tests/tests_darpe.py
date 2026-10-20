import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from ColorAdminApp.modules.darpe import RESOURCES, _regional_rows, _with_canonical_commons, api_resource, export_cadastros_excel, import_cadastros, page
from ColorAdminApp.module_access import MODULE_DARPE, allowed_modules, primary_module


def request_for(path, method="get", body=None):
    factory = RequestFactory()
    request = (factory.get(path) if method == "get" else
               getattr(factory, method)(path, data=json.dumps(body or {}), content_type="application/json"))
    request.session = {"authenticated": True, "user_id": "user-1", "user_profile": {
        "user_id": "user-1", "role_id": 2, "sector": "D.A.R.P.E", "access_level": "regional",
        "full_name": "Operador DARPE",
    }}
    return request


class DarpeModuleTests(SimpleTestCase):
    def test_only_regional_municipalities_are_listed(self):
        rows = [{"cidade": "COTIA"}, {"cidade": "OSASCO"}, {"cidade": "SANTANA DE PARNAÍBA"}]
        self.assertEqual([row["cidade"] for row in _regional_rows(rows)], ["COTIA", "SANTANA DE PARNAIBA"])

    def test_city_grouping_uses_one_official_spelling(self):
        rows = [{"cidade": "Cotia", "nome_completo": "A"}, {"cidade": "COTIA", "nome_completo": "B"}]
        self.assertEqual([row["cidade"] for row in _regional_rows(rows)], ["COTIA", "COTIA"])

    @patch("ColorAdminApp.modules.darpe.common_catalog", return_value=[{
        "comum": "BR-22-0673 - VILA DOUTOR CARDOSO", "cidade": "ITAPEVI",
    }])
    def test_common_uses_regional_br_code_without_changing_legacy_value(self, _catalog):
        result = _with_canonical_commons([{
            "comum_congregacao": "VILA DOUTOR CARDOSO", "cidade": "ITAPEVI",
        }])[0]
        self.assertEqual(result["comum_congregacao"], "VILA DOUTOR CARDOSO")
        self.assertEqual(result["comum_exibicao"], "BR-22-0673 - VILA DOUTOR CARDOSO")

    def test_sector_has_own_module(self):
        self.assertEqual(primary_module({"sector": "D.A.R.P.E"}), MODULE_DARPE)
        with patch("ColorAdminApp.module_access.explicit_modules", return_value=set()):
            self.assertEqual(allowed_modules(request_for("/darpe/")), {MODULE_DARPE})

    def test_page_renders_cadastros(self):
        response = page(request_for("/darpe/cadastros/"), "cadastros")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dados do D.A.R.P.E")
        self.assertContains(response, "Importar")
        self.assertContains(response, "select2.full.min.js")

    def test_import_requires_workbook(self):
        response = import_cadastros(request_for("/darpe/api/cadastros/importar/", "post"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("planilha oficial", response.content.decode("utf-8"))

    @patch("ColorAdminApp.modules.darpe.requests.get")
    def test_excel_uses_institutional_header_and_phone_format(self, get):
        from io import BytesIO
        from openpyxl import load_workbook
        response_mock = Mock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = [{"id": "x", "nome_completo": "Pessoa Teste",
            "comum_congregacao": "CENTRAL", "cidade": "ITAPEVI", "ddd": "11",
            "telefone": "912345678", "status": "ATIVO", "darpe_atendente": True}]
        get.return_value = response_mock
        response = export_cadastros_excel(request_for("/darpe/api/cadastros/exportar-excel/"))
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["A1"].value, "CONGREGAÇÃO CRISTÃ NO BRASIL")
        self.assertEqual(sheet["A3"].value, "D.A.R.P.E")
        self.assertEqual(sheet["D7"].value, "(11) 9 1234-5678")
        self.assertEqual(sheet.freeze_panes, "A7")
        self.assertFalse(sheet.sheet_view.showGridLines)

    @patch("ColorAdminApp.modules.darpe.requests.post")
    def test_cadastro_records_server_side_authorship(self, post):
        response_mock = Mock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = [{"id": "saved", "nome_completo": "Pessoa Teste"}]
        post.return_value = response_mock
        response = api_resource(request_for("/darpe/api/cadastros/", "post", {
            "nome_completo": "Pessoa Teste", "comum_congregacao": "CENTRAL DE ITAPEVI", "status": "ATIVO",
            "created_by_name": "Nome forjado",
        }), "cadastros")
        self.assertEqual(response.status_code, 201)
        saved = post.call_args.kwargs["json"]
        self.assertEqual(saved["created_by_name"], "Operador DARPE")
        self.assertEqual(saved["updated_by_user_id"], "user-1")

    def test_spreadsheet_fields_are_covered(self):
        expected = {"cpf", "nome_completo", "instrumento_oficializado", "rg", "data_nascimento", "sexo",
                    "estado_civil", "comum_congregacao", "data_batismo", "logradouro", "numero", "complemento",
                    "bairro", "cidade", "uf", "cep", "ddd", "telefone", "darpe_ministerio", "darpe_atendente",
                    "darpe_colaborador", "darpe_encarregado", "darpe_musico_organista", "darpe_grupo_canto",
                    "declaracao_local", "declaracao_data", "nome_ministerio", "nome_encarregado_orquestra",
                    "nome_voluntario"}
        self.assertTrue(expected.issubset(RESOURCES["cadastros"]["fields"]))
