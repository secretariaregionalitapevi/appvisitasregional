import io
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve
from openpyxl import load_workbook

from ColorAdminApp.sam_audit import export_excel


class SamAuditExportTests(SimpleTestCase):
    def request(self):
        request = RequestFactory().get("/gem/sam/historico/exportar-excel/?action=presenca")
        request.session = {"user_profile": {"role_id": 2, "role": "Regional", "full_name": "Operador Regional"}}
        return request

    @patch("ColorAdminApp.sam_audit._all_filtered_events")
    @patch("ColorAdminApp.sam_audit._allowed", return_value=True)
    def test_excel_uses_institutional_header_and_human_identity(self, _allowed, events):
        events.return_value = [{
            "occurred_at": "2026-09-27T12:25:58+00:00", "actor_name_snapshot": "OPERADOR",
            "congregation_snapshot": "JARDIM JUREMA", "action_type": "presenca",
            "action_raw": "Marcou presenca da matricula: 1991614", "device": "Computador",
            "platform": "Windows 10", "ip_address": "127.0.0.1", "parsed_refs": {"attendance_id": 1991614},
            "resolution": {"primary_name": "SILVIO GARCIA DAS NEVES", "student": {"name": "SILVIO GARCIA DAS NEVES"},
                           "class": {"source_id": 462941, "date": "2026-09-27", "instructor": "INSTRUTOR"},
                           "group": {"name": "AVANCADO 2026/2029", "course": "TEORIA MUSICAL",
                                     "members": [{"name": "SILVIO GARCIA DAS NEVES"}]}}
        }]
        response = export_excel(self.request())
        workbook = load_workbook(io.BytesIO(response.content))
        sheet = workbook["HISTORICO SAM"]
        self.assertEqual(sheet["A1"].value, "CONGREGAÇÃO CRISTÃ NO BRASIL")
        self.assertEqual(sheet["A2"].value, "Regional Itapevi - São Paulo")
        self.assertEqual(sheet["F8"].value, "SILVIO GARCIA DAS NEVES")
        self.assertEqual(sheet["J8"].value, 462941)
        self.assertEqual(sheet.freeze_panes, "A8")
        self.assertIn("Historico_SAM_", response["Content-Disposition"])

    def test_export_routes_are_registered(self):
        self.assertEqual(resolve("/gem/sam/historico/relatorio/").url_name, "samAuditReportData")
        self.assertEqual(resolve("/gem/sam/historico/exportar-excel/").url_name, "samAuditExcel")
        self.assertEqual(resolve("/gem/sam/historico/exportar-pdf/").url_name, "samAuditPdf")

    def test_page_has_executive_exports_and_no_access_audit_warning(self):
        content = (Path(__file__).parent / "templates" / "pages" / "sam_audit.html").read_text(encoding="utf-8")
        self.assertIn('id="excel"', content)
        self.assertIn('id="pdf"', content)
        self.assertIn('id="municipio"', content)
        self.assertIn('id="comum"', content)
        self.assertIn("CONGREGAÇÃO CRISTÃ NO BRASIL", content)
        self.assertNotIn("Esta página não é a Auditoria de acesso", content)

    def test_location_filters_initialize_with_the_gem_component(self):
        content = (Path(__file__).parent / "templates" / "pages" / "sam_audit.html").read_text(encoding="utf-8")
        self.assertIn("function setupGemFilter(selector)", content)
        self.assertIn("['#municipio', '#comum'].forEach(setupGemFilter)", content)
        self.assertIn("function updateCommonOptions()", content)
        self.assertNotIn('id="search"', content)
        self.assertNotIn(">Gerar</button>", content)
        self.assertIn("$('#municipio').addEventListener('change'", content)
        self.assertNotIn("forEach(setupLocationFilter)", content)
        self.assertIn(".gem-check-filter.open .gem-check-menu", content)
        self.assertIn("Instrutor da última aula", content)
        self.assertIn("Referência do lançamento neste evento", content)
        self.assertIn("Último método documentado", content)
        self.assertIn("Origem do vínculo", content)

    def test_page_has_bottom_pagination_for_long_event_lists(self):
        content = (Path(__file__).parent / "templates" / "pages" / "sam_audit.html").read_text(encoding="utf-8")
        self.assertIn('id="range-note"', content)
        self.assertIn('id="prev-bottom"', content)
        self.assertIn('id="next-bottom"', content)
        self.assertIn("$('#next-bottom').onclick", content)

    def test_action_badges_have_distinct_palette_classes(self):
        content = (Path(__file__).parent / "templates" / "pages" / "sam_audit.html").read_text(encoding="utf-8")
        for action in ("acesso", "presenca", "licao", "aula", "turma", "tarefa", "aluno", "usuario", "ata", "fase", "outro"):
            self.assertIn(f".type.{action}{{", content)
        self.assertIn("fase: 'Fase'", content)
