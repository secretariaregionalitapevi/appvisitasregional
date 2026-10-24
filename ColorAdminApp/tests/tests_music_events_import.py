import io
import json
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from openpyxl import Workbook

from ColorAdminApp.modules.music_events_import import parse_workbook
from ColorAdminApp.modules import music_events


class AppContParserTests(SimpleTestCase):
    def workbook(self, records, header=None):
        book = Workbook()
        sheet = book.active
        sheet.title = 'Dados'
        sheet.append(header or ['UUID','NOME COMPLETO','COMUM','CIDADE','CARGO','NÍVEL',
                      'INSTRUMENTO','NAIPE_INSTRUMENTO','LOCAL_ENSAIO','DATA_ENSAIO','REGISTRADO_POR'])
        for row in records:
            sheet.append(row)
        old = book.create_sheet('Resumo antigo')
        old.append(['Total', 9999])
        stream = io.BytesIO()
        book.save(stream)
        return stream.getvalue()

    def row(self, identity=None, name='Pessoa de teste', cargo='INSTRUTOR', instrument='VIOLINO', family='CORDAS', local='ITAPEVI'):
        return [identity or str(uuid4()),name,'BR-22-1 - Comum','ITAPEVI',cargo,'RJM',instrument,family,local,datetime(2026,9,20,8,30),'Operador legado']

    def test_deduplicates_uuid_keeps_last_and_ignores_summary(self):
        row = self.row()
        newer = row[:]
        newer[5] = 'OFICIALIZADO'
        parsed = parse_workbook(self.workbook([row,newer]))
        self.assertEqual(parsed['raw_count'], 2)
        self.assertEqual(parsed['count'], 1)
        self.assertEqual(parsed['duplicates'], 1)
        self.assertEqual(parsed['records'][0]['nivel'], 'OFICIALIZADO')
        self.assertEqual(parsed['categories'], {'MUSICO': 1})
        self.assertEqual(parsed['records'][0]['data_hora_original'], '2026-09-20T08:30:00')

    def test_same_uuid_at_different_location_is_blocked(self):
        row = self.row()
        other = row[:]
        other[8] = 'PIRAPORA'
        with self.assertRaisesRegex(ValueError, 'local diferente'):
            parse_workbook(self.workbook([row,other]))

    def test_same_name_different_uuid_is_not_silently_removed(self):
        result = parse_workbook(self.workbook([self.row(),self.row()]))
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['possible_duplicates'], 1)

    def test_organist_role_and_support_are_separate(self):
        result = parse_workbook(self.workbook([
            self.row(cargo='EXAMINADORA DE ORGANISTAS',instrument='ÓRGÃO',family='TECLADO'),
            self.row(cargo='PORTEIRO (A)',instrument='',family=''),
        ]))
        self.assertEqual(result['categories'], {'ORGANISTA':1,'APOIO':1})

    def test_formula_and_invalid_file_are_rejected(self):
        row = self.row()
        row[1] = '=1+1'
        with self.assertRaisesRegex(ValueError,'fórmula'):
            parse_workbook(self.workbook([row]))
        with self.assertRaises(ValueError):
            parse_workbook(b'not an excel')


@override_settings(SUPABASE_URL='https://db.example',SUPABASE_SERVICE_ROLE_KEY='test')
class AppContApiTests(SimpleTestCase):
    def request(self, data):
        request = RequestFactory().post('/musica/eventos/api/importacao/confirmar/',
            data=json.dumps(data),content_type='application/json')
        request.session = {'authenticated':True,'user_id':'actor-1',
                           'user_profile':{'full_name':'Operador autenticado','role_id':1}}
        return request

    def setUp(self):
        cache.clear()
        cache.set('music-events-import:actor-1:token-1',{'sha256':'a'*64,'records':[{'nome':'Teste','local':'ITAPEVI'}]},1800)

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'user_scope',return_value={'level':'global'})
    @patch.object(music_events.requests,'post')
    def test_may_import_rejects_cotia_before_writing(self, post, scope, allowed):
        cache.set('music-events-import:actor-1:token-1',{'sha256':'a'*64,'records':[{'nome':'Teste','local':'COTIA'}]},1800)
        request = self.request({'token':'token-1','titulo':'Ensaio de maio','tipo':'ENSAIO_REGIONAL',
                               'data_evento':'2026-05-17','conferido':True})
        response = music_events.api_import(request,'confirmar')
        self.assertEqual(response.status_code,400)
        self.assertIn('COTIA',response.content.decode())
        post.assert_not_called()

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'user_scope',return_value={'level':'global'})
    @patch.object(music_events.requests,'post')
    def test_confirmation_requires_explicit_review(self, post, scope, allowed):
        result = music_events.api_import(self.request({'token':'token-1','data_evento':'2026-09-20'}),'confirmar')
        self.assertEqual(result.status_code,400)
        post.assert_not_called()

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'user_scope',return_value={'level':'global'})
    @patch.object(music_events.requests,'post')
    def test_token_is_bound_to_operator(self, post, scope, allowed):
        request = self.request({'token':'token-1'})
        request.session['user_id'] = 'other-user'
        self.assertEqual(music_events.api_import(request,'confirmar').status_code,400)
        post.assert_not_called()

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'user_scope',return_value={'level':'global'})
    @patch.object(music_events.requests,'post')
    def test_confirmation_uses_atomic_rpc_and_authenticated_actor(self, post, scope, allowed):
        post.return_value = Mock()
        post.return_value.json.return_value = {'evento_id':'event','quantidade':1}
        request = self.request({'token':'token-1','titulo':'Ensaio de teste','tipo':'ENSAIO_REGIONAL',
            'data_evento':'2026-09-20','conferido':True,'p_usuario_nome':'Forjado'})
        result = music_events.api_import(request,'confirmar')
        self.assertEqual(result.status_code,200)
        self.assertIn('/rpc/musica_evento_importar_appcont',post.call_args.args[0])
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['p_usuario_nome'],'Operador autenticado')
        self.assertEqual(payload['p_usuario_id'],'actor-1')
        self.assertEqual(payload['p_familia'],'GERAL')

    @patch.object(music_events,'_allowed',return_value=True)
    @patch.object(music_events,'user_scope',return_value={'level':'municipal'})
    @patch.object(music_events.requests,'post')
    def test_municipal_import_is_denied(self, post, scope, allowed):
        self.assertEqual(music_events.api_import(self.request({}),'confirmar').status_code,403)
        post.assert_not_called()
