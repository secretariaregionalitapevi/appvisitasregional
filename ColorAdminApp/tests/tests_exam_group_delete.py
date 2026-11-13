import json
import uuid
from unittest.mock import Mock, patch
import requests
from django.test import RequestFactory, SimpleTestCase
from ColorAdminApp import exam_group_delete as deletion


class ExamGroupDeletionTests(SimpleTestCase):
    def setUp(self):
        self.group={'administracao':'ITAPEVI','categoria':'Organistas','data_exame':'2026-11-07'}
        self.session={'user_profile':{'role_id':1,'full_name':'Operador de teste'}}
        self.rows=[dict(id=str(uuid.UUID(int=i+1)),municipio='ITAPEVI',comum='BR-22-1234 - CENTRAL',categoria='ORGANISTA',
                        instrumento='ÓRGÃO',data_exame='2026-11-07',updated_at='2026-11-13T12:00:00Z') for i in range(23)]

    def post(self,data,session=None):
        request=RequestFactory().post('/musica/exames/api/excluir-grupo/',json.dumps(data),content_type='application/json')
        request.session=self.session if session is None else session
        return deletion.api_delete_group(request)

    @patch('ColorAdminApp.exam_group_delete.exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.exam_group_delete.group_rows')
    @patch('ColorAdminApp.exam_group_delete.delete_batch')
    def test_entire_group_uses_all_pages_with_a_bound_preview(self,delete,rows,access):
        current={r['id']:r for r in self.rows}
        rows.side_effect=lambda *args:list(current.values())
        def remove(batch):
            ids={r['id'] for r in batch}
            for record_id in ids:current.pop(record_id)
            return ids
        delete.side_effect=remove
        preview=self.post({'acao':'previa','modo':'todos','grupo':self.group})
        body=json.loads(preview.content)
        self.assertEqual(body['quantidade'],23)
        delete.assert_not_called()
        other=self.post({'acao':'confirmar','token':body['token']},session={'user_profile':{'role_id':1}})
        self.assertEqual(other.status_code,409);delete.assert_not_called()
        first=json.loads(self.post({'acao':'confirmar','token':body['token']}).content)
        self.assertEqual((first['excluidos'],first['restantes']),(20,3))
        second=json.loads(self.post({'acao':'confirmar','token':body['token']}).content)
        self.assertEqual((second['excluidos'],second['restantes']),(23,0))
        self.assertEqual(len(delete.call_args_list[0].args[0]),20)
        self.assertEqual(len(delete.call_args_list[1].args[0]),3)

    @patch('ColorAdminApp.exam_group_delete.exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.exam_group_delete.group_rows')
    @patch('ColorAdminApp.exam_group_delete.delete_batch')
    def test_selected_records_do_not_delete_unselected_group_members(self,delete,rows,access):
        rows.return_value=self.rows
        delete.side_effect=lambda batch:{r['id'] for r in batch}
        ids=[self.rows[0]['id'],self.rows[20]['id']]
        preview=json.loads(self.post({'acao':'previa','modo':'selecionados','grupo':self.group,'ids':ids}).content)
        response=self.post({'acao':'confirmar','token':preview['token']})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual({r['id'] for r in delete.call_args.args[0]},set(ids))

    @patch('ColorAdminApp.exam_group_delete.exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.exam_group_delete.group_rows')
    @patch('ColorAdminApp.exam_group_delete.delete_batch')
    def test_new_records_or_edits_after_preview_require_a_new_confirmation(self,delete,rows,access):
        rows.return_value=self.rows
        preview=json.loads(self.post({'acao':'previa','modo':'todos','grupo':self.group}).content)
        rows.return_value=self.rows+[dict(self.rows[0],id=str(uuid.uuid4()))]
        self.assertEqual(self.post({'acao':'confirmar','token':preview['token']}).status_code,409)
        delete.assert_not_called()
        rows.return_value=self.rows
        preview=json.loads(self.post({'acao':'previa','modo':'selecionados','grupo':self.group,'ids':[self.rows[0]['id']]}).content)
        rows.return_value=[dict(self.rows[0],observacoes='Alterado sem atualizar o timestamp'),*self.rows[1:]]
        self.assertEqual(self.post({'acao':'confirmar','token':preview['token']}).status_code,409)
        delete.assert_not_called()

    @patch('ColorAdminApp.exam_group_delete.exams.can_open_module',return_value=True)
    @patch('ColorAdminApp.exam_group_delete.group_rows')
    @patch('ColorAdminApp.exam_group_delete.delete_batch')
    def test_ids_outside_the_selected_group_are_rejected_before_deleting(self,delete,rows,access):
        rows.return_value=self.rows
        response=self.post({'acao':'previa','modo':'selecionados','grupo':self.group,'ids':[str(uuid.uuid4())]})
        self.assertEqual(response.status_code,409)
        delete.assert_not_called()

    @patch('ColorAdminApp.exam_group_delete.exams.can_open_module',return_value=False)
    @patch('ColorAdminApp.exam_group_delete.requests.delete')
    def test_access_is_required(self,delete,access):
        self.assertEqual(self.post({'acao':'previa','modo':'todos','grupo':self.group}).status_code,403)
        delete.assert_not_called()

    @patch('ColorAdminApp.exam_group_delete.requests.get')
    def test_group_query_checks_scope_category_date_and_joint_administration(self,get):
        request=RequestFactory().get('/')
        request.session={'user_profile':{'access_level':'municipal','municipio':'CAUCAIA DO ALTO'}}
        group=deletion.parse_group(dict(self.group,administracao='COTIA / CAUCAIA / VGP'))
        get.return_value.json.return_value=[dict(self.rows[0],municipio='CAUCAIA DO ALTO'),dict(self.rows[1],municipio='COTIA'),
                                          dict(self.rows[2],municipio='CAUCAIA DO ALTO',categoria='MÚSICO',instrumento='VIOLINO')]
        rows=deletion.group_rows(request,group)
        self.assertEqual([r['id'] for r in rows],[self.rows[0]['id']])
        self.assertEqual(get.call_args.kwargs['params']['municipio'],'eq.CAUCAIA DO ALTO')
        self.assertFalse(deletion.matches_group(dict(self.rows[0],data_exame='2026-10-10'),group))

    @patch('ColorAdminApp.exam_group_delete.requests.delete')
    def test_delete_batch_removes_only_explicit_ids_from_both_tables(self,delete):
        delete.return_value.json.return_value=[{'id':r['id']} for r in self.rows[:2]]
        self.assertEqual(deletion.delete_batch(self.rows[:2]),{r['id'] for r in self.rows[:2]})
        self.assertEqual(delete.call_count,2)
        for call in delete.call_args_list:
            self.assertEqual(call.kwargs['params'],{'id':'in.('+','.join(r['id'] for r in self.rows[:2])+')'})

    @patch('ColorAdminApp.exam_group_delete.exams.sync_shared_exam')
    @patch('ColorAdminApp.exam_group_delete.requests.get')
    @patch('ColorAdminApp.exam_group_delete.requests.delete')
    def test_uncertain_delete_restores_only_confirmed_remaining_mirrors(self,delete,get,sync):
        failure=Mock();failure.raise_for_status.side_effect=requests.Timeout('lost acknowledgement')
        delete.side_effect=[Mock(),failure]
        get.return_value.json.return_value=[self.rows[1]]
        with self.assertRaises(requests.RequestException):
            deletion.delete_batch(self.rows[:2])
        sync.assert_called_once_with(self.rows[1])
