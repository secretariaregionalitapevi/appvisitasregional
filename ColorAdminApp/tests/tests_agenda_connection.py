import json
from unittest.mock import Mock, patch
import requests
from django.test import RequestFactory, SimpleTestCase
from ColorAdminApp.views import apiVisitasAgenda
from ColorAdminApp.utils.supabase_http import supabase_get

CATALOG=[{'comum':'BR-22-2054 - CH\u00c1CARA REGINA','cidade':'ITAPEVI'}]

def response(rows,status=200):
    return Mock(status_code=status,json=lambda:rows)

@patch('ColorAdminApp.utils.supabase_http.time.sleep')
class SupabaseReadRecoveryTests(SimpleTestCase):
    @patch('ColorAdminApp.utils.supabase_http.requests.get')
    def test_tls_eof_recovers_with_a_fresh_read_without_disabling_verification(self,get,sleep):
        expected=response([]);get.side_effect=[requests.exceptions.SSLError('UNEXPECTED_EOF_WHILE_READING'),expected]
        self.assertIs(supabase_get('https://example.test/rest/v1/visitas_agenda'),expected)
        self.assertEqual(get.call_count,2)
        self.assertTrue(all(call.kwargs.get('verify',True) is True for call in get.call_args_list))

    @patch('ColorAdminApp.utils.supabase_http.requests.get')
    def test_persistent_tls_failure_is_bounded(self,get,sleep):
        get.side_effect=requests.exceptions.SSLError('EOF')
        with self.assertRaises(requests.exceptions.SSLError):supabase_get('https://example.test')
        self.assertEqual(get.call_count,3)

    @patch('ColorAdminApp.utils.supabase_http.requests.get')
    def test_gateway_failure_recovers_but_permission_errors_are_not_retried(self,get,sleep):
        expected=response([]);get.side_effect=[response({},503),expected]
        self.assertIs(supabase_get('https://example.test'),expected)
        get.reset_mock();denied=response({},403);get.side_effect=None;get.return_value=denied
        self.assertIs(supabase_get('https://example.test'),denied)
        get.assert_called_once()

@patch('ColorAdminApp.views.user_scope',return_value={'level':'global','municipio':'ITAPEVI','comum':''})
@patch('ColorAdminApp.views.visible_commons',return_value=CATALOG)
@patch('ColorAdminApp.utils.supabase_http.time.sleep')
class AgendaConnectionTests(SimpleTestCase):
    def request(self):
        return RequestFactory().get('/visitas/api/agenda/',{'comum':CATALOG[0]['comum'],'start_date':'2026-10-01T00:00:00-03:00','end_date':'2026-11-01T00:00:00-03:00'})

    @patch('ColorAdminApp.views.requests.get')
    def test_empty_calendar_after_deletion_does_not_fetch_members(self,get,sleep,commons,scope):
        get.side_effect=[requests.exceptions.SSLError('EOF'),response([])]
        result=apiVisitasAgenda(self.request())
        self.assertEqual(result.status_code,200)
        self.assertEqual(json.loads(result.content),[])
        self.assertEqual(get.call_count,2)
        self.assertTrue(all('visitas_agenda' in call.args[0] for call in get.call_args_list))

    @patch('ColorAdminApp.views.requests.delete')
    @patch('ColorAdminApp.views.requests.post')
    @patch('ColorAdminApp.views.requests.get')
    def test_persistent_read_failure_returns_503_and_never_writes(self,get,post,delete,sleep,commons,scope):
        get.side_effect=requests.exceptions.SSLError('EOF')
        result=apiVisitasAgenda(self.request())
        self.assertEqual(result.status_code,503)
        self.assertEqual(json.loads(result.content)['code'],'AGENDA_UNAVAILABLE')
        self.assertTrue(json.loads(result.content)['retryable'])
        self.assertEqual(get.call_count,3)
        post.assert_not_called();delete.assert_not_called()

    @patch('ColorAdminApp.views.requests.get')
    def test_member_lookup_recovers_without_repeating_initial_calendar_read(self,get,sleep,commons,scope):
        get.side_effect=[response([{'id':'v','irmandade_id':'m','observacoes':''}]),requests.exceptions.SSLError('EOF'),response([{'id':'m','comum':CATALOG[0]['comum']}])]
        result=apiVisitasAgenda(self.request())
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(json.loads(result.content)),1)
        self.assertEqual(get.call_count,3)
        self.assertIn('visitas_irmandade',get.call_args_list[-1].args[0])

    @patch('ColorAdminApp.views.log_audit')
    @patch('ColorAdminApp.views.requests.delete',return_value=response([]))
    @patch('ColorAdminApp.views.requests.get')
    def test_successful_delete_is_not_repeated_when_calendar_refresh_fails(self,get,delete,audit,sleep,commons,scope):
        visit_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        get.side_effect=[response([{'id':visit_id}])]+[requests.exceptions.SSLError('EOF')]*3
        req=RequestFactory().delete('/visitas/api/agenda/?id='+visit_id)
        self.assertEqual(apiVisitasAgenda(req).status_code,200)
        self.assertEqual(apiVisitasAgenda(self.request()).status_code,503)
        delete.assert_called_once()
        audit.assert_called_once()
