from django.test import SimpleTestCase

from .sam_portal_history import portal_report_to_export


class SamPortalHistoryTests(SimpleTestCase):
    def test_msa_preserves_observation_and_authorizer_exactly(self):
        report = {"student": "Abner", "tabs": {"MSA": {"tables": [{
            "headers": ["Data da Lição", "Fases", "Paginas", "Lições", "Claves", "Observações", "Autorizante", "Ações"],
            "rows": [["15/08/2026", "7.7 - 7.7", "75 - 75", "55 - 55", "Sol", "Solfejo do hino 67.", "ENIVALDO RIBEIRO DE SOUZA", "Apagar"]],
        }]}}}
        event = portal_report_to_export(report)["students"][0]["history"]["msa"][0]
        self.assertEqual(event["observacoes"], "Solfejo do hino 67.")
        self.assertEqual(event["autorizado_por"], "ENIVALDO RIBEIRO DE SOUZA")

    def test_group_msa_is_split_into_fields(self):
        report = {"student": "Aluno", "tabs": {"MSA": {"tables": [{
            "headers": ["Páginas", "Observações", "Data da Lição"],
            "rows": [["Fase(s): de 16.1 até 16.3;\nPágina(s): de 136 até 138", "", "06/06/2026"]],
        }]}}}
        event = portal_report_to_export(report)["students"][0]["history"]["msa"][0]
        self.assertEqual(event["fase"], "16.1 - 16.3")
        self.assertEqual(event["paginas"], "136 - 138")
        self.assertEqual(event["data_aula"], "2026-06-06")

    def test_hinario_without_date_is_not_imported(self):
        report = {"student": "Aluno", "tabs": {"HinÃ¡rio": {"tables": [{
            "headers": ["Data da Aula", "Hino", "ObservaÃ§Ãµes"],
            "rows": [["", "", "Foi Feito o Ensaio do GEM"]],
        }]}}}
        history = portal_report_to_export(report)["students"][0]["history"]
        self.assertEqual(history["hinario"], [])

    def test_hinario_without_number_is_not_imported(self):
        report = {"student": "Aluno", "tabs": {"Hinário": {"tables": [{
            "headers": ["Data da Aula", "Hino", "Voz", "Observações"],
            "rows": [["07/06/2026", "", "Voz", "JÁ TOCA TODOS HINOS"]],
        }]}}}
        history = portal_report_to_export(report)["students"][0]["history"]
        self.assertEqual(history["hinario"], [])
