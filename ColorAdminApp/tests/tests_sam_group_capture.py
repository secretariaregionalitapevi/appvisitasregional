from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from ColorAdminApp import sam_group_capture as capture
from ColorAdminApp.sam_class_mirror import parse_group_row


def form(source_id="10", responsible=True):
    values = {"id_curso":"1", "descricao":"TURMA", "id_igreja":"4446", "dia_semana":"6",
              "dt_inicio":"07/02/2026", "dt_fim":"25/11/2028", "hr_inicio":"09:30:00",
              "hr_fim":"11:00:00", "id_turma_genero":"1"}
    text = '<form action="https://musical.congregacao.org.br/turmas/atualizar">'
    text += f'<input name="id" value="{source_id}">'
    text += ''.join(f'<input name="{k}" value="{v}">' for k,v in values.items())
    text += '<select name="id_responsavel"></select><select name="id_responsavel2"></select>'
    text += '<input type="checkbox" name="status" value="1" checked></form>'
    if responsible:
        text += """<script>const option = '<option value="25" selected>RESPONSÁVEL - COMUM</option>';
        $('#id_responsavel').append(option).trigger('change');</script>"""
    return text


class GroupCaptureTests(SimpleTestCase):
    def test_captures_dynamic_responsible_and_dates(self):
        x = capture.parse_registration(form(), "10")
        self.assertTrue(x["complete"])
        self.assertEqual(x["fields"]["id_responsavel"], "25")
        self.assertEqual(x["fields"]["hr_fim"], "11:00:00")
        self.assertEqual(x["fields"]["dt_fim"], "25/11/2028")
        self.assertEqual(x["fields"]["id_responsavel2"], "")
        self.assertEqual(x["labels"]["id_responsavel"], "RESPONSÁVEL - COMUM")

    def test_rejects_wrong_identity_and_login_page(self):
        for html in (form("11"), '<form action="/login"></form>'):
            with self.assertRaises(ValueError):capture.parse_registration(html, "10")

    def test_missing_responsible_is_not_called_complete(self):
        x=capture.parse_registration(form(responsible=False), "10")
        self.assertFalse(x["complete"])
        self.assertIn("id_responsavel", x["missing_fields"])

    def test_unchecked_status_and_weekday_zero_are_preserved(self):
        x=capture.parse_registration(form().replace(' checked','').replace('name="dia_semana" value="6"','name="dia_semana" value="0"'), "10")
        self.assertEqual(x["fields"]["status"], "0")
        self.assertEqual(x["fields"]["dia_semana"], "0")

    def test_rejects_missing_field_and_invalid_date(self):
        for html in (form().replace('name="hr_fim"', 'name="other"'), form().replace('07/02/2026','31/02/2026')):
            with self.assertRaises(ValueError):capture.parse_registration(html, "10")

    def test_both_list_states_are_required_to_cover_all_groups(self):
        one=['10','COMUM','CURSO','TURMA','1','07/02/2026','25/11/2028','SÁB','1','10']
        two=['11','COMUM','CURSO','OUTRA','1','07/02/2026','25/11/2028','SÁB','1','11']
        with patch.object(capture,'fetch_group_page',side_effect=[
            {"recordsTotal":2,"recordsFiltered":1,"data":[one]},
            {"recordsTotal":2,"recordsFiltered":1,"data":[two]}]) as fetch:
            rows=capture.read_groups(Mock())
        self.assertEqual(set(rows),{"10","11"})
        self.assertEqual([c.kwargs["status"] for c in fetch.call_args_list],[0,1])

    def test_missing_group_from_union_blocks_refresh(self):
        one=['10','COMUM','CURSO','TURMA','1','07/02/2026','25/11/2028','SÁB','1','10']
        with patch.object(capture,'fetch_group_page',return_value={"recordsTotal":2,"recordsFiltered":1,"data":[one]}):
            with self.assertRaises(ValueError):capture.read_groups(Mock())

    def test_numeric_list_status_is_not_interpreted_as_false(self):
        x=parse_group_row(['10','COMUM','CURSO','TURMA','1','07/02/2026','25/11/2028','SÁB','1','10'])
        self.assertTrue(x["ativo"])

    def test_refresh_preserves_payload_metadata_and_uuid(self):
        old={"id":"uuid", "source_id":10,"source_payload":{"metadata":"keep"}}
        command=SimpleNamespace(_get_all=Mock(return_value=[old]),_upsert=Mock(),stdout=StringIO())
        page=Mock();page.evaluate.return_value=[{"id":"10","ok":True,"html":form()}]
        row=['10','COMUM','CURSO','TURMA','1','07/02/2026','25/11/2028','SÁB','1','10']
        with patch.object(capture,'fetch_group_page',return_value={"recordsFiltered":1,"data":[row]}):
            result=capture.sync_groups(command,page)
        self.assertEqual(result["updated"],1)
        saved=command._upsert.call_args.args[1][0]
        self.assertEqual(saved["source_payload"]["metadata"],"keep")
        self.assertEqual(saved["source_payload"]["registration"]["fields"]["id_responsavel"],"25")
        self.assertNotIn("id",saved)
        self.assertEqual(command._upsert.call_args.args[2],"source_id")

    def test_deleted_group_is_kept_without_inventing_registration(self):
        command=SimpleNamespace(_get_all=Mock(return_value=[{"source_id":10}]),_upsert=Mock(),stdout=StringIO())
        page=Mock();page.evaluate.return_value=[{"id":"10","ok":False,"status":404}]
        with patch.object(capture,'fetch_group_page',return_value={"recordsFiltered":0,"data":[]}):
            result=capture.sync_groups(command,page)
        self.assertEqual(result["updated"],0)
        self.assertEqual(len(result["failures"]),1)
        command._upsert.assert_not_called()

    def test_recent_registration_skips_fetch_unless_forced(self):
        row=['10','COMUM','CURSO','TURMA','1','07/02/2026','25/11/2028','SÁB','1','10']
        registration=capture.parse_registration(form(), "10")
        registration["listing_hash"]=parse_group_row(row)["source_hash"]
        command=SimpleNamespace(_get_all=Mock(return_value=[{"source_id":10,"source_payload":{"registration":registration}}]),_upsert=Mock(),stdout=StringIO())
        page=Mock();page.evaluate.return_value=[{"id":"10","ok":True,"html":form()}]
        with patch.object(capture,'fetch_group_page',return_value={"recordsFiltered":1,"data":[row]}):
            result=capture.sync_groups(command,page)
            self.assertEqual(result["recent_unchanged"],1)
            page.evaluate.assert_not_called()
            result=capture.sync_groups(command,page,force=True)
            self.assertEqual(result["updated"],1)
            page.evaluate.assert_called_once()

    def test_changed_listing_refreshes_recent_registration(self):
        row=['10','COMUM','CURSO','TURMA','1','07/02/2026','25/11/2028','SÁB','1','10']
        registration=capture.parse_registration(form(), "10");registration["listing_hash"]="old"
        command=SimpleNamespace(_get_all=Mock(return_value=[{"source_id":10,"source_payload":{"registration":registration}}]),_upsert=Mock(),stdout=StringIO())
        page=Mock();page.evaluate.return_value=[{"id":"10","ok":True,"html":form()}]
        with patch.object(capture,'fetch_group_page',return_value={"recordsFiltered":1,"data":[row]}):
            result=capture.sync_groups(command,page)
        self.assertEqual(result["updated"],1)
        page.evaluate.assert_called_once()

    def test_truncated_listing_cannot_start_updates(self):
        command=SimpleNamespace(_get_all=Mock(return_value=[]),_upsert=Mock(),stdout=StringIO())
        with patch.object(capture,'fetch_group_page',return_value={"recordsFiltered":1,"data":[]}):
            with self.assertRaises(ValueError):capture.sync_groups(command,Mock())
        command._upsert.assert_not_called()
