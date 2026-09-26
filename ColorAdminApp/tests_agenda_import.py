from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import Workbook

from .agenda_import import import_key, match_member, parse_workbook, prepare_rows


class AgendaImportParserTests(SimpleTestCase):
    def test_new_member_is_repeatable_and_meeting_has_no_team(self):
        from .agenda_import import row_payload
        raw = {'date': '2026-10-05', 'time': '20:00', 'host': 'Tereza',
               'address': 'Rua Francelina, 06', 'category': 'RF', 'attendant': 'Alcides Sousa'}
        row = prepare_rows([raw], 'COMUM TESTE', [], [], [])[0]
        again = prepare_rows([raw], 'COMUM TESTE', [], [], [])[0]
        self.assertEqual(row['state'], 'ready')
        self.assertTrue(row['create_member'])
        self.assertEqual(row['member_id'], again['member_id'])
        self.assertIn('Novo cadastro', row['message'])
        payload = row_payload(row, 'agenda.xlsx', 'abc')
        self.assertIsNone(payload['equipe_id'])
        self.assertIsNone(payload['equipe_responsavel'])

    def test_missing_address_does_not_block_other_rows(self):
        rows = prepare_rows([
            {'date': '2026-10-05', 'time': '20:00', 'host': 'Tereza', 'address': '', 'category': 'RF'},
            {'date': '2026-10-06', 'time': '20:00', 'host': 'Tereza', 'address': 'Rua Francelina, 06', 'category': 'RF'},
        ], 'COMUM TESTE', [], [], [])
        self.assertEqual([r['state'] for r in rows], ['error', 'ready'])

    def test_reads_calendar_workbook_without_changing_member_data(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["OUTUBRO 2026"])
        sheet.append(["Data", "Sem", "Hrs", "Na casa da Irmã(o)", "Endereço/Referência", "Atende"])
        sheet.append(["12/10", "SEG", "20:00", "IRMÃ ILDA", "Rua Esterlízia, 31", "REINALDO FAUSTINO"])
        stream = BytesIO()
        workbook.save(stream)

        rows = parse_workbook(stream.getvalue())

        self.assertEqual(rows, [{
            "date": "2026-10-12", "time": "20:00", "host": "Ilda",
            "address": "Rua Esterlízia, 31", "category": "RF",
            "attendant": "Reinaldo Faustino",
        }])

    def test_reconciles_short_document_name_to_unique_registered_name(self):
        members = [{"id": "1", "nome": "Ilda de Oliveira", "endereco": "Rua Esterlízia, 31"}]
        member, kind = match_member({"host": "Ilda", "address": "Rua Esterlízia, 31"}, members)
        self.assertEqual(member["id"], "1")
        self.assertEqual(kind, "first_name")

    def test_ignores_coordinate_prefix_when_matching_address_number(self):
        members = [{
            "id": "1", "nome": "Hilda",
            "endereco": "[-23.5400851, -46.9255114] Rua Esterlízia, 31 Itapevi - SP",
        }]
        member, kind = match_member({"host": "Ilda", "address": "Rua Esterlízia, 31"}, members)
        self.assertEqual(member["id"], "1")
        self.assertEqual(kind, "fuzzy")

    def test_existing_same_day_category_and_member_is_duplicate_even_at_other_time(self):
        row = {"date": "2026-10-12", "time": "20:00", "host": "Ilda",
               "address": "Rua Esterlízia, 31", "category": "RF", "attendant": "Reinaldo"}
        members = [{"id": "m1", "nome": "Ilda", "endereco": "Rua Esterlízia, 31",
                    "setor": "Vila Doutor Cardoso", "equipe_id": "t1"}]
        teams = [{"id": "t1", "nome": "Equipe 1", "tipo": "LOCAL"}]
        existing = [{"id": "a1", "irmandade_id": "m1", "data_inicio": "2026-10-12T19:30:00-03:00",
                     "categoria": "RF", "status": "Marcada", "endereco_visitado": "Rua Esterlízia, 31"}]

        prepared = prepare_rows([row], "COMUM TESTE", members, teams, existing)

        self.assertEqual(prepared[0]["state"], "duplicate")
        self.assertEqual(prepared[0]["import_key"], import_key("COMUM TESTE", row, "m1"))
