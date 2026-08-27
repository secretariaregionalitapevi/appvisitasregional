from django.test import SimpleTestCase

from .sam_history_sync import event_payload, event_signature, match_student


class SamHistorySyncTests(SimpleTestCase):
    def setUp(self):
        self.targets = [
            {"id": "1", "nome_aluno": "JOÃO DA SILVA", "comum_congregacao": "BR-22-0001 - CENTRAL", "municipio": "ITAPEVI", "instrumento": "VIOLINO"},
            {"id": "2", "nome_aluno": "JOÃO DA SILVA", "comum_congregacao": "BR-22-0002 - JARDIM", "municipio": "JANDIRA", "instrumento": "TROMPETE"},
        ]

    def test_match_requires_unique_name_and_common(self):
        target, status = match_student({"nome": "João da Silva", "comum": "BR-22-0002 - JARDIM NOVO"}, self.targets)
        self.assertEqual(status, "matched")
        self.assertEqual(target["id"], "2")

    def test_match_accepts_common_name_without_br_code(self):
        target, status = match_student({"nome": "João da Silva", "comum": "JARDIM"}, self.targets)
        self.assertEqual(status, "matched")
        self.assertEqual(target["id"], "2")

    def test_same_name_without_common_is_ambiguous(self):
        target, status = match_student({"nome": "João da Silva"}, self.targets)
        self.assertIsNone(target)
        self.assertEqual(status, "ambiguous")

    def test_event_signature_is_stable_and_student_specific(self):
        event = {"data_aula": "2026-08-01", "fase": "Fase 3", "licoes": "1 a 4"}
        first = event_payload("msa", event, self.targets[0])
        second = event_payload("msa", event, self.targets[1])
        self.assertEqual(event_signature("msa", first), event_signature("msa", dict(reversed(list(first.items())))))
        self.assertNotEqual(event_signature("msa", first), event_signature("msa", second))
