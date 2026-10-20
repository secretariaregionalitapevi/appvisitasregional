from unittest.mock import patch

from django.test import SimpleTestCase

from ColorAdminApp.sam_audit_enrichment import enrich_events


class SamAuditEnrichmentTests(SimpleTestCase):
    @patch("ColorAdminApp.sam_audit_enrichment._get")
    def test_attendance_id_resolves_student_class_group_and_members(self, get):
        def rows(table, params, limit=5000):
            return {
                "sam_gem_attendance": [{"source_frequency_id": 1991614, "source_member_id": 867635,
                                         "nome_aluno": "ALUNO IDENTIFICADO", "presente": True,
                                         "aula_id": "class-uuid"}],
                "sam_gem_classes": [{"id": "class-uuid", "source_id": 462941, "turma_id": "group-uuid",
                                      "data_aula": "2026-09-27", "inicio": "09:00", "termino": "11:00",
                                      "curso": "TEORIA MUSICAL", "turma": "TURMA A",
                                      "congregacao": "JARDIM JUREMA", "instrutor_aula": "INSTRUTOR"}],
                "sam_gem_groups": [{"id": "group-uuid", "source_id": 63999, "turma": "TURMA A",
                                     "curso": "TEORIA MUSICAL", "congregacao": "JARDIM JUREMA",
                                     "data_inicio": "2026-01-10", "data_termino": None, "ativo": True}],
                "sam_gem_enrollments": [{"turma_id": "group-uuid", "source_member_id": 867635,
                                          "nome_aluno": "ALUNO IDENTIFICADO", "instrumento": "VIOLINO",
                                          "congregacao": "JARDIM JUREMA", "ativo": True}],
            }.get(table, [])
        get.side_effect = rows

        result = enrich_events([{"parsed_refs": {"attendance_id": 1991614}, "target_type": "matricula"}])[0]

        self.assertTrue(result["resolution"]["resolved"])
        self.assertEqual(result["resolution"]["primary_name"], "ALUNO IDENTIFICADO")
        self.assertEqual(result["resolution"]["class"]["source_id"], 462941)
        self.assertEqual(result["resolution"]["group"]["start_date"], "2026-01-10")
        self.assertEqual(result["resolution"]["group"]["members"][0]["name"], "ALUNO IDENTIFICADO")

    @patch("ColorAdminApp.sam_audit_enrichment._get", return_value=[])
    def test_unavailable_mirror_keeps_event_unresolved_without_losing_id(self, _get):
        result = enrich_events([{"parsed_refs": {"class_id": 999}, "target_type": "aula"}])[0]
        self.assertFalse(result["resolution"]["resolved"])
        self.assertEqual(result["parsed_refs"]["class_id"], 999)

    @patch("ColorAdminApp.sam_audit_enrichment._get")
    def test_student_reference_resolves_current_class_and_latest_method(self, get):
        group_id = "group-uuid"
        student_uuid = "student-uuid"
        enrollment = {
            "id": "enrollment-uuid", "source_member_id": 543184, "aluno_id": student_uuid,
            "turma_id": group_id, "nome_aluno": "JONATHAS DE JESUS DO NASCIMENTO",
            "congregacao": "ITAPEVI CENTRAL", "instrumento": "VIOLINO",
        }

        def rows(table, params, limit=5000):
            if table == "sam_gem_attendance":
                return [{"source_member_id": 543184, "nome_aluno": "JONATHAS DE JESUS DO NASCIMENTO"}] * 2
            if table == "sam_gem_enrollments":
                return [enrollment]
            if table == "sam_gem_groups":
                return [{"id": group_id, "source_id": 40707, "turma": "PERÍODO 4",
                         "curso": "TEORIA MUSICAL", "congregacao": "ITAPEVI CENTRAL",
                         "dia_horario": None, "ativo": True}]
            if table == "sam_gem_classes":
                return [{"id": "class-uuid", "source_id": 461908, "turma_id": group_id,
                         "data_aula": "2026-09-19", "inicio": "14:10:00", "termino": "14:50:00",
                         "curso": "TEORIA MUSICAL", "turma": "PERÍODO 4",
                         "congregacao": "ITAPEVI CENTRAL", "instrutor_aula": "VALDENIR MOREIRA"}]
            if table == "musica_acompanhamento_metodo":
                return [{"id": "method-uuid", "aluno_id": student_uuid, "data_inicio": "2026-08-22",
                         "metodo": "2° SCHMOLL", "pagina": "28", "licao": "60",
                         "autorizado_por": "IGOR CARDAMONE SUNCURSO"}]
            return []

        get.side_effect = rows
        result = enrich_events([{
            "target_type": "metodo", "target_source_id": 857465,
            "parsed_refs": {"method_id": 857465, "student_id": 543184},
        }])[0]

        resolution = result["resolution"]
        self.assertEqual(resolution["primary_name"], "JONATHAS DE JESUS DO NASCIMENTO")
        self.assertEqual(resolution["class"]["instructor"], "VALDENIR MOREIRA")
        self.assertEqual(resolution["class"]["start"], "14:10:00")
        self.assertEqual(resolution["class"]["end"], "14:50:00")
        self.assertEqual(resolution["latest_method"]["metodo"], "2° SCHMOLL")
        self.assertEqual(resolution["method_reference_id"], 857465)
