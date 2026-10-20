import json
from unittest.mock import Mock, patch

import requests
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from ColorAdminApp.sam_audit import (
    _associate_adjacent_student, _filter_by_location, api_event_detail, api_events,
    api_location_options, api_sync_status, page,
)
from ColorAdminApp.sam_audit_parser import classify_action, parse_log_row, parse_references


class SamAuditParserTests(SimpleTestCase):
    def test_attendance_ids_are_extracted(self):
        refs, kind, source_id = parse_references("Marcou presenca do aluno id = 867635, na aula id=460499")
        self.assertEqual(refs, {"student_id": 867635, "class_id": 460499})
        self.assertEqual((kind, source_id), ("aluno", 867635))

    def test_event_keeps_identity_snapshot_and_is_idempotent(self):
        row = ["91", "NATHAN VAZ DOS SANTOS", "JARDIM RUTH", "Marcou presenca do aluno id = 867635, na aula id=460499", "21/09/2026 10:54:38", "Computador", "Windows 10", "172.71.238.37"]
        first, second = parse_log_row(row), parse_log_row(row)
        self.assertEqual(first["actor_name_snapshot"], "NATHAN VAZ DOS SANTOS")
        self.assertEqual(first["source_fingerprint"], second["source_fingerprint"])
        self.assertEqual(first["action_type"], "presenca")
        self.assertEqual(first["target_source_id"], 867635)

    def test_common_sam_actions_are_classified(self):
        self.assertEqual(classify_action("Criou nova turma"), "turma")
        self.assertEqual(classify_action("Solicitou recuperacao de senha"), "usuario")
        self.assertEqual(classify_action("Salvou ata: 42534"), "ata")
        self.assertEqual(classify_action("Acessou o Sistema"), "acesso")

    def test_attendance_record_id_is_extracted(self):
        refs, kind, source_id = parse_references("Marcou presenca da matricula: 1991614")
        self.assertEqual(refs["attendance_id"], 1991614)
        self.assertEqual((kind, source_id), ("matricula", 1991614))

    def test_open_class_colon_uses_canonical_class_reference(self):
        refs, kind, source_id = parse_references("Abriu aula: 462941")
        self.assertEqual(refs, {"class_id": 462941})
        self.assertEqual((kind, source_id), ("aula", 462941))

    def test_method_lesson_reference_is_preserved(self):
        refs, kind, source_id = parse_references("Cadastrou Lição do Método: 857465")
        self.assertEqual(refs, {"method_id": 857465})
        self.assertEqual((kind, source_id), ("metodo", 857465))

    def test_hymn_log_keeps_both_student_and_hymn_ids(self):
        refs, kind, source_id = parse_references(
            "Cadastrou Hino: P-131 -> Aluno: 543184id hinário: 518805"
        )
        self.assertEqual(refs, {"student_id": 543184, "hymn_id": 518805})
        self.assertEqual((kind, source_id), ("hinario", 518805))


class SamAuditRoutesTests(SimpleTestCase):
    def test_routes_are_separate_from_user_audit(self):
        self.assertEqual(resolve("/gem/sam/historico/").url_name, "samAudit")
        self.assertEqual(resolve("/gem/sam/historico/api/").url_name, "samAuditApi")
        self.assertEqual(resolve("/gem/sam/historico/api/sync/").url_name, "samAuditSyncStatus")
        self.assertEqual(resolve("/gem/sam/historico/api/00000000-0000-0000-0000-000000000001/").url_name,
                 "samAuditEventDetail")

    def test_page_rejects_non_regional_user(self):
        request = RequestFactory().get("/gem/sam/historico/")
        request.session = {"user_profile": {"role_id": 99, "role": "Membro"}}
        response = page(request)
        self.assertEqual(response.status_code, 403)

    def test_page_renders_utf8_text(self):
        request = RequestFactory().get("/gem/sam/historico/")
        request.session = {"user_profile": {"role_id": 2, "sector": "Musicalização", "full_name": "Operador Teste"}}
        response = page(request)
        self.assertEqual(response.status_code, 200)
        content = response.render().content.decode("utf-8")
        self.assertIn("Histórico SAM", content)
        self.assertNotIn("HistÃ³rico SAM", content)
        self.assertNotIn("PreservaÃ§Ã£o permanente", content)

    def test_location_options_include_common_municipality_relation(self):
        request = RequestFactory().get("/gem/sam/historico/filtros/")
        request.session = {"user_profile": {"role_id": 2}}

        with (
            patch("ColorAdminApp.sam_audit._allowed", return_value=True),
            patch("ColorAdminApp.sam_audit.common_catalog", return_value=[
                {"cidade": "Cotia", "comum": "BR-21-0797 - JABOTICABEIRA"},
                {"cidade": "Itapevi", "comum": "CENTRAL"},
            ]),
        ):
            response = api_location_options(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["commons"][0]["municipality"], "Cotia")

    def test_events_api_fetches_only_requested_page_and_uses_database_count(self):
        request = RequestFactory().get("/gem/sam/historico/api/?page=2&page_size=20")
        request.session = {"user_profile": {"role_id": 2}}
        events_response = Mock(headers={"Content-Range": "20-20/123"})
        events_response.json.return_value = [{"action_raw": "Evento de teste"}]
        cursor_response = Mock()
        cursor_response.raise_for_status.side_effect = requests.Timeout("cursor indisponível")

        with (
            patch("ColorAdminApp.sam_audit._allowed", return_value=True),
            patch("ColorAdminApp.sam_audit.service_headers", side_effect=lambda prefer=None: {"Prefer": prefer} if prefer else {}),
            patch("ColorAdminApp.sam_audit.enrich_events") as enrich,
            patch("ColorAdminApp.sam_audit.requests.get", side_effect=[events_response, cursor_response]) as get,
        ):
            response = api_events(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["total"], 123)
        self.assertEqual(json.loads(response.content)["sync"], {})
        self.assertEqual(get.call_args_list[0].kwargs["params"]["offset"], 20)
        self.assertEqual(get.call_args_list[0].kwargs["params"]["limit"], 20)
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["Prefer"], "count=exact")
        self.assertEqual(get.call_count, 1)
        enrich.assert_not_called()

    def test_events_api_caps_page_size_at_fifty(self):
        request = RequestFactory().get("/gem/sam/historico/api/?page=1&page_size=300")
        request.session = {"user_profile": {"role_id": 2}}
        events_response = Mock(headers={"Content-Range": "0-49/79"})
        events_response.json.return_value = []

        with (
            patch("ColorAdminApp.sam_audit._allowed", return_value=True),
            patch("ColorAdminApp.sam_audit.service_headers", return_value={}),
            patch("ColorAdminApp.sam_audit.requests.get", return_value=events_response) as get,
        ):
            response = api_events(request)

        payload = json.loads(response.content)
        self.assertEqual(payload["page_size"], 50)
        self.assertEqual(get.call_args.kwargs["params"]["limit"], 50)

    def test_sync_status_is_loaded_from_its_own_short_request(self):
        request = RequestFactory().get("/gem/sam/historico/api/sync/")
        request.session = {"user_profile": {"role_id": 2}}
        response_mock = Mock()
        response_mock.json.return_value = [{"last_incremental_sync_at": "2026-10-01T12:00:00Z"}]

        with (
            patch("ColorAdminApp.sam_audit._allowed", return_value=True),
            patch("ColorAdminApp.sam_audit.service_headers", return_value={}),
            patch("ColorAdminApp.sam_audit.requests.get", return_value=response_mock) as get,
        ):
            response = api_sync_status(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["sync"]["last_incremental_sync_at"],
                         "2026-10-01T12:00:00Z")
        self.assertEqual(get.call_args.kwargs["timeout"], (1.5, 2.5))

    def test_event_details_enrich_only_the_requested_event(self):
        event_id = "00000000-0000-0000-0000-000000000001"
        request = RequestFactory().get(f"/gem/sam/historico/api/{event_id}/")
        request.session = {"user_profile": {"role_id": 2}}
        response_mock = Mock()
        response_mock.json.return_value = [{"id": event_id, "action_raw": "Evento de teste"}]

        with (
            patch("ColorAdminApp.sam_audit._allowed", return_value=True),
            patch("ColorAdminApp.sam_audit.service_headers", return_value={}),
            patch("ColorAdminApp.sam_audit.requests.get", return_value=response_mock) as get,
            patch("ColorAdminApp.sam_audit.enrich_events", side_effect=lambda rows: rows) as enrich,
        ):
            response = api_event_detail(request, event_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["event"]["id"], event_id)
        self.assertEqual(get.call_args.kwargs["params"]["id"], f"eq.{event_id}")
        enrich.assert_called_once_with([{
            "id": event_id, "action_raw": "Evento de teste", "parsed_refs": {},
            "target_type": None, "target_source_id": None,
        }])

    def test_method_event_uses_unique_adjacent_student_reference(self):
        event = {
            "id": "method-event", "occurred_at": "2026-09-29T21:43:03+00:00",
            "actor_name_snapshot": "OPERADOR", "congregation_snapshot": "ITAPEVI CENTRAL",
            "action_raw": "Cadastrou Lição do Método: 857465", "target_type": "metodo",
            "parsed_refs": {"method_id": 857465},
        }
        response = Mock()
        response.json.return_value = [{
            "id": "hymn-event", "occurred_at": "2026-09-29T21:43:07+00:00",
            "action_raw": "Cadastrou Hino: -> Aluno: 543184id hinário: 518805",
            "parsed_refs": {"student_id": 543184},
        }]

        with patch("ColorAdminApp.sam_audit.requests.get", return_value=response) as get:
            result = _associate_adjacent_student(event)

        self.assertEqual(result["parsed_refs"]["student_id"], 543184)
        self.assertEqual(result["resolution_context"]["confidence"], "inferred")
        self.assertEqual(result["resolution_context"]["time_delta_seconds"], 4)
        self.assertEqual(get.call_args.kwargs["params"]["actor_name_snapshot"], "eq.OPERADOR")
        self.assertEqual(get.call_args.kwargs["params"]["congregation_snapshot"], "eq.ITAPEVI CENTRAL")

    def test_method_event_remains_unlinked_when_adjacent_logs_name_two_students(self):
        event = {
            "id": "method-event", "occurred_at": "2026-09-29T21:43:03+00:00",
            "actor_name_snapshot": "OPERADOR", "congregation_snapshot": "ITAPEVI CENTRAL",
            "target_type": "metodo", "parsed_refs": {"method_id": 857465},
        }
        response = Mock()
        response.json.return_value = [
            {"id": "hymn-a", "occurred_at": "2026-09-29T21:43:04+00:00",
             "action_raw": "Aluno: 543184", "parsed_refs": {"student_id": 543184}},
            {"id": "hymn-b", "occurred_at": "2026-09-29T21:43:05+00:00",
             "action_raw": "Aluno: 543185", "parsed_refs": {"student_id": 543185}},
        ]

        with patch("ColorAdminApp.sam_audit.requests.get", return_value=response):
            result = _associate_adjacent_student(event)

        self.assertNotIn("student_id", result["parsed_refs"])
        self.assertNotIn("resolution_context", result)

    def test_location_filters_are_applied_before_pagination(self):
        request = RequestFactory().get(
            "/gem/sam/historico/api/?page=2&page_size=20&municipio=Itapevi&comum=BR-21-1039+-+CENTRAL+DE+ITAPEVI"
        )
        request.session = {"user_profile": {"role_id": 2}}
        events_response = Mock(headers={"Content-Range": "20-20/21"})
        events_response.json.return_value = [{"action_raw": "Evento local"}]
        cursor_response = Mock()
        cursor_response.json.return_value = [{}]

        with patch("ColorAdminApp.sam_audit._allowed", return_value=True), \
                patch("ColorAdminApp.sam_audit.common_catalog", return_value=[
                    {"cidade": "ITAPEVI", "comum": "BR-21-1039 - CENTRAL DE ITAPEVI"},
                    {"cidade": "CAUCAIA DO ALTO", "comum": "BR-21-0001 - CENTRAL"},
                    {"cidade": "NOVA PIRAPORA", "comum": "BR-21-0002 - CENTRAL"},
                ]), \
                patch("ColorAdminApp.sam_audit.service_headers", side_effect=lambda prefer=None: {"Prefer": prefer} if prefer else {}), \
                patch("ColorAdminApp.sam_audit.enrich_events", side_effect=lambda rows: rows), \
                patch("ColorAdminApp.sam_audit._all_filtered_events") as scan, \
                patch("ColorAdminApp.sam_audit.requests.get", side_effect=[events_response, cursor_response]) as get:
            response = api_events(request)

        self.assertEqual(response.status_code, 200)
        query = get.call_args_list[0].kwargs["params"]
        snapshot_filter = query["congregation_snapshot"]
        self.assertIn('"ITAPEVI CENTRAL"', snapshot_filter)
        self.assertIn('"CENTRAL DE ITAPEVI"', snapshot_filter)
        self.assertNotIn('"CENTRAL"', snapshot_filter)
        self.assertEqual(query["offset"], 20)
        scan.assert_not_called()

    def test_report_location_filter_matches_legacy_common_snapshot(self):
        request = RequestFactory().get("/report/", {
            "municipio": "ITAPEVI", "comum": "BR-21-1039 - CENTRAL DE ITAPEVI",
        })
        rows = [
            {"congregation_snapshot": "ITAPEVI CENTRAL"},
            {"congregation_snapshot": "CAUCAIA DO ALTO - CENTRAL"},
        ]
        catalog = [
            {"cidade": "ITAPEVI", "comum": "BR-21-1039 - CENTRAL DE ITAPEVI"},
            {"cidade": "CAUCAIA DO ALTO", "comum": "BR-21-0001 - CENTRAL"},
            {"cidade": "NOVA PIRAPORA", "comum": "BR-21-0002 - CENTRAL"},
        ]

        with patch("ColorAdminApp.sam_audit.common_catalog", return_value=catalog):
            filtered = _filter_by_location(request, rows)

        self.assertEqual(filtered, [rows[0]])
