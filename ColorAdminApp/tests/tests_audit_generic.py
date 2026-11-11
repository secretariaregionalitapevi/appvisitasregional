from datetime import datetime, timezone
import json
from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory

from ColorAdminApp.modules.audit_generic import (
    api_audit_generic,
    canonical_common,
    collect_admin,
    collect_gem,
    collect_musicalizacao,
    format_datetime_br,
    format_date_br,
    compute_relative_time,
    clean_common,
    canonical_operator_name,
    get_action_badge_meta,
)


class AuditGenericTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.session = {"user_profile": {"role_id": 1, "role": "Master", "sector": "Global"}}

    def test_format_helpers(self):
        self.assertEqual(
            clean_common("BR-22-0673 - VILA DOUTOR CARDOSO"),
            "BR-22-0673 - VILA DOUTOR CARDOSO",
        )
        self.assertEqual(clean_common("Jardim Miranda"), "Jardim Miranda")
        self.assertEqual(canonical_operator_name("RICARDO GRANGEIRO"), "Ricardo Grangeiro")
        self.assertEqual(canonical_operator_name("Ricardo Grangieiro"), "Ricardo Grangeiro")
        self.assertEqual(format_date_br("2026-11-08"), "08/11/2026")
        self.assertEqual(
            format_datetime_br("2026-11-10T19:30:00+00:00"),
            "10/11/2026 16:30",
        )

        now_ref = datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(compute_relative_time("2026-11-10T14:29:40+00:00", now_ref), "agora mesmo")
        self.assertEqual(compute_relative_time("2026-11-10T14:15:00+00:00", now_ref), "há 15 min")
        self.assertEqual(compute_relative_time("2026-11-10T11:30:00+00:00", now_ref), "há 3 h")
        self.assertEqual(compute_relative_time("2026-11-09T14:30:00+00:00", now_ref), "ontem")

    def test_action_badge_meta(self):
        meta_create = get_action_badge_meta("CREATE")
        self.assertEqual(meta_create["code"], "CREATE")
        self.assertEqual(meta_create["label"], "Criação")

        meta_update = get_action_badge_meta("UPDATE")
        self.assertEqual(meta_update["label"], "Atualização")

        meta_delete = get_action_badge_meta("DELETE")
        self.assertEqual(meta_delete["label"], "Exclusão")

    @patch(
        "ColorAdminApp.modules.audit_generic.common_catalog",
        return_value=[
            {
                "comum": "BR-22-0673 - VILA DOUTOR CARDOSO",
                "cidade": "ITAPEVI",
            }
        ],
    )
    def test_canonical_common_restores_official_code(self, mock_common_catalog):
        self.assertEqual(
            canonical_common("VILA DOUTOR CARDOSO"),
            "BR-22-0673 - VILA DOUTOR CARDOSO",
        )
        self.assertEqual(
            canonical_common("BR-22-0673 - VILA DOUTOR CARDOSO"),
            "BR-22-0673 - VILA DOUTOR CARDOSO",
        )
        mock_common_catalog.assert_called_once()

    @patch("ColorAdminApp.modules.audit_generic.fetch_table")
    def test_admin_audit_uses_operator_profile_common(self, mock_fetch):
        mock_fetch.side_effect = [
            [
                {
                    "id": "log-1",
                    "user_id": "user-1",
                    "action": "VIEW_PAGE",
                    "module": "NAVIGATION",
                    "details": {
                        "actor": {
                            "name": "Ricardo Grangieiro",
                            "scope": "Global",
                        }
                    },
                    "created_at": "2026-11-10T19:00:00+00:00",
                }
            ],
            [
                {
                    "user_id": "user-1",
                    "full_name": "Ricardo Grangeiro",
                    "comum": "BR-22-0673 - VILA DOUTOR CARDOSO",
                }
            ],
        ]

        records = collect_admin("2026-11-01T00:00:00+00:00")

        self.assertEqual(records[0]["created_by"], "Ricardo Grangeiro")
        self.assertEqual(
            records[0]["location"],
            "BR-22-0673 - VILA DOUTOR CARDOSO",
        )
        self.assertEqual(records[0]["source_label"], "Auditoria administrativa do APP")

    @patch("ColorAdminApp.modules.audit_generic.fetch_table")
    def test_gem_audit_uses_authorized_sam_user_for_legacy_records(self, mock_fetch):
        mock_fetch.side_effect = [
            [
                {
                    "id": "student-1",
                    "nome_aluno": "Aluno de Teste",
                    "instrumento": "TROMPETE",
                    "nivel": "CANDIDATO(A)",
                    "status": "Ativo",
                    "comum_congregacao": "BR-22-0673 - VILA DOUTOR CARDOSO",
                    "municipio": "ITAPEVI",
                    "created_at": "2026-11-10T19:00:00+00:00",
                    "updated_at": "2026-11-10T19:00:00+00:00",
                }
            ],
            [
                {
                    "aluno_id": "student-1",
                    "autorizado_por": "Ricardo Grangeiro",
                    "data_aula": "2026-11-10",
                }
            ],
            [],
            [],
            [],
            [],
        ]

        records = collect_gem("2026-11-01T00:00:00+00:00")

        self.assertEqual(records[0]["created_by"], "Ricardo Grangeiro")
        self.assertEqual(records[0]["source_label"], "Lançamento autorizado no SAM")
        self.assertEqual(records[0]["detail_fields"]["status"], "Ativo")
        self.assertEqual(records[0]["raw_data"]["lancado_por"], None)
        self.assertEqual(
            records[0]["raw_data"]["responsavel_lancamento_sam"],
            "Ricardo Grangeiro",
        )

    @patch("ColorAdminApp.modules.audit_generic.fetch_table")
    def test_gem_audit_identifies_catalog_synchronization_without_author(self, mock_fetch):
        mock_fetch.side_effect = [
            [
                {
                    "id": "student-1",
                    "nome_aluno": "Aluno de Catálogo",
                    "instrumento": "TROMPETE",
                    "nivel": "CANDIDATO(A)",
                    "status": "Ativo",
                    "comum_congregacao": "BR-22-0673 - VILA DOUTOR CARDOSO",
                    "municipio": "ITAPEVI",
                    "created_at": "2026-11-10T19:00:00+00:00",
                    "updated_at": "2026-11-10T19:00:00+00:00",
                }
            ],
            [],
            [],
            [],
            [],
            [],
        ]

        records = collect_gem("2026-11-01T00:00:00+00:00")

        self.assertEqual(records[0]["created_by"], "Sistema SAM — sincronização de catálogo")
        self.assertEqual(records[0]["source_label"], "Sincronização do catálogo SAM")

    @patch("ColorAdminApp.modules.audit_generic.fetch_table")
    def test_api_audit_generic_musicalizacao(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": "1",
                "data_aula": "2026-11-08",
                "cidade": "ITAPEVI",
                "polo": "BR-22-0673 - VILA DOUTOR CARDOSO",
                "nome_atividade": "Ritmo e Movimento",
                "meninos_presentes": 5,
                "meninas_presentes": 4,
                "instrutores_presentes": 2,
                "created_by_name": "Instrutor Teste",
                "created_at": "2026-11-08T13:30:00+00:00",
            }
        ]
        req = self.rf.get("/api/auditoria/generic/?module=musicalizacao&period=30")
        req.session = self.session
        resp = api_audit_generic(req, "musicalizacao")
        self.assertEqual(resp.status_code, 200)

        data = json.loads(resp.content)
        self.assertGreaterEqual(data["total_events"], 1)
        self.assertIn("records", data)
        first = data["records"][0]
        self.assertEqual(first["module"], "musicalizacao")
        self.assertIn("Ritmo e Movimento", first["details"])
        self.assertIn("VILA DOUTOR CARDOSO", first["details"])
        self.assertEqual(first["created_by"], "Instrutor Teste")
        self.assertIn("timeline_series", data)
        self.assertIn("executive_note", data)

    @patch("ColorAdminApp.modules.audit_generic.fetch_table")
    def test_api_audit_generic_filters_action(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": "1",
                "data_aula": "2026-11-08",
                "cidade": "ITAPEVI",
                "polo": "BR-22-0673 - VILA DOUTOR CARDOSO",
                "created_at": "2026-11-08T13:30:00+00:00",
                "created_by_name": "A",
            },
            {
                "id": "2",
                "data_aula": "2026-11-08",
                "cidade": "ITAPEVI",
                "polo": "BR-22-0673 - VILA DOUTOR CARDOSO",
                "created_at": "2026-11-08T13:30:00+00:00",
                "updated_by_name": "B",
                "created_by_name": "A",
            }
        ]
        # Filtrar apenas por UPDATE
        req = self.rf.get("/api/auditoria/generic/?module=musicalizacao&action=UPDATE")
        req.session = self.session
        resp = api_audit_generic(req, "musicalizacao")
        data = json.loads(resp.content)
        self.assertTrue(all(r["action"] == "UPDATE" for r in data["records"]))

    @patch("ColorAdminApp.modules.audit_generic.is_global", return_value=False)
    @patch(
        "ColorAdminApp.modules.audit_generic.can_access_module",
        side_effect=lambda request, module: module == "musicalizacao",
    )
    @patch("ColorAdminApp.modules.audit_generic.fetch_table")
    def test_api_audit_generic_limits_all_modules_to_authorized_access(
        self, mock_fetch, mock_module_access, mock_is_global
    ):
        mock_fetch.return_value = [
            {
                "id": "1",
                "data_aula": "2026-11-08",
                "cidade": "ITAPEVI",
                "polo": "BR-22-0673 - VILA DOUTOR CARDOSO",
                "created_at": "2026-11-08T13:30:00+00:00",
                "created_by_name": "Instrutor Teste",
            }
        ]
        req = self.rf.get("/api/auditoria/generic/?module=all&period=30")
        req.session = self.session

        response = api_audit_generic(req, "all")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["records"])
        self.assertTrue(all(record["module"] == "musicalizacao" for record in data["records"]))
        self.assertTrue(mock_module_access.called)

    def test_api_audit_generic_filters_foreign_and_unlocated_records_by_server_scope(self):
        common = "BR-22-0673 - VILA DOUTOR CARDOSO"
        records = [
            {
                "id": "local",
                "module": "musicalizacao",
                "action": "CREATE",
                "created_by": "Instrutor",
                "created_at": "2026-11-08T13:30:00+00:00",
                "location": "ITAPEVI · " + common,
                "details": "Registro local",
                "raw_data": {"polo": common, "cidade": "ITAPEVI"},
            },
            {
                "id": "foreign",
                "module": "musicalizacao",
                "action": "DELETE",
                "created_by": "Instrutor",
                "created_at": "2026-11-08T13:31:00+00:00",
                "location": "JANDIRA · BR-99-9999 - OUTRA COMUM",
                "details": "Registro de outra localidade",
                "raw_data": {"polo": "BR-99-9999 - OUTRA COMUM", "cidade": "JANDIRA"},
            },
            {
                "id": "unlocated",
                "module": "musicalizacao",
                "action": "CREATE",
                "created_by": "Instrutor",
                "created_at": "2026-11-08T13:32:00+00:00",
                "location": "Polo de Musicalização",
                "details": "Registro sem local confiável",
                "raw_data": {},
            },
        ]
        scope = {
            "level": "local",
            "comum": common,
            "municipio": "ITAPEVI",
            "profile": {"role_id": 4},
        }
        req = self.rf.get("/api/auditoria/generic/?module=musicalizacao&period=30")
        req.session = {"user_profile": scope["profile"], "user_id": "user-1"}

        with patch("ColorAdminApp.modules.audit_generic.user_scope", return_value=scope), \
             patch("ColorAdminApp.modules.audit_generic.is_global", return_value=False), \
             patch("ColorAdminApp.modules.audit_generic.can_access_module", return_value=True), \
             patch.dict("ColorAdminApp.modules.audit_generic.COLLECTORS", {
                 "musicalizacao": lambda cutoff, limit: records,
             }):
            response = api_audit_generic(req, "musicalizacao")

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in payload["records"]], ["local"])
        self.assertEqual(payload["total_events"], 1)
        self.assertEqual(payload["action_counts"]["deletes"], 0)

    @patch("ColorAdminApp.modules.audit_generic.fetch_table")
    def test_musicalizacao_attendance_audit_uses_lesson_location(self, mock_fetch):
        mock_fetch.side_effect = [
            [],
            [],
            [{
                "id": "presence-1",
                "aula_id": "lesson-1",
                "aluno_id": "student-1",
                "presente": True,
                "created_at": "2026-11-08T13:30:00+00:00",
            }],
            [{"id": "lesson-1", "cidade": "ITAPEVI", "polo": "BR-22-0673 - VILA DOUTOR CARDOSO"}],
        ]

        records = collect_musicalizacao("2026-11-01T00:00:00+00:00", limit=2)

        attendance = next(record for record in records if record["resource"] == "Frequência e Chamadas")
        self.assertEqual(attendance["raw_data"]["cidade"], "ITAPEVI")
        self.assertEqual(attendance["raw_data"]["polo"], "BR-22-0673 - VILA DOUTOR CARDOSO")
