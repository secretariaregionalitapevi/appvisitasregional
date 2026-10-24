import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from ColorAdminApp.modules import music_events


@override_settings(SUPABASE_URL='https://db.example', SUPABASE_SERVICE_ROLE_KEY='test')
class MusicEventsTests(SimpleTestCase):
    def request(self, method='get', payload=None):
        request = getattr(RequestFactory(), method)('/musica/eventos/api/eventos/',
            data=json.dumps(payload or {}) if method == 'post' else {}, content_type='application/json')
        request.session = {'authenticated': True, 'user_id': 'operator-1',
                           'user_profile': {'full_name': 'Operador regional', 'role_id': 1}}
        return request

    @patch('ColorAdminApp.module_access.allowed_modules', return_value={'musicalizacao'})
    @patch('ColorAdminApp.utils.context_processors.resolve')
    def test_music_menu_is_visible_for_authorized_non_master(self, resolve, modules):
        from ColorAdminApp.utils.context_processors import sidebar_menu
        request = self.request()
        request.session['user_profile']['role_id'] = 2
        resolve.return_value.url_name = 'musicEvents'
        menu = sidebar_menu(request)['sidebar_menu']
        music = next(item for item in menu if item.get('title') == 'Música')
        self.assertTrue(any(child.get('name') == 'musicEvents' for child in music['children']))

    @patch.object(music_events, 'can_open_module', return_value=True)
    def test_no_authenticated_session_is_denied(self, access):
        request = self.request()
        request.session = {}
        self.assertEqual(music_events.api_events(request).status_code, 403)

    @patch.object(music_events, '_allowed', return_value=True)
    @patch.object(music_events, 'user_scope', return_value={'level': 'local'})
    @patch.object(music_events.requests, 'post')
    def test_local_user_cannot_create(self, post, scope, allowed):
        result = music_events.api_events(self.request('post'))
        self.assertEqual(result.status_code, 403)
        post.assert_not_called()

    @patch.object(music_events, '_allowed', return_value=True)
    @patch.object(music_events, 'user_scope', return_value={'level': 'regional'})
    @patch.object(music_events, '_read', return_value=[{'id': 'base-1'}])
    @patch.object(music_events.requests, 'post')
    def test_draft_creator_comes_from_session(self, post, read, scope, allowed):
        post.return_value = Mock()
        post.return_value.json.return_value = [{'id': 'event-1'}]
        result = music_events.api_events(self.request('post', {
            'titulo': 'Ensaio regional', 'data_evento': '2026-10-19',
            'tipo': 'ENSAIO_REGIONAL', 'base_id': 'base-1',
            'created_by_name': 'Nome forjado', 'status': 'ABERTO',
        }))
        self.assertEqual(result.status_code, 201)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['created_by_user_id'], 'operator-1')
        self.assertEqual(payload['created_by_name'], 'Operador regional')
        self.assertEqual(payload['status'], 'RASCUNHO')
        self.assertEqual(payload['familia'], 'GERAL')

    @patch.object(music_events, '_allowed', return_value=True)
    @patch.object(music_events, 'user_scope', return_value={'level': 'regional'})
    @patch.object(music_events, '_read', return_value=[])
    @patch.object(music_events.requests, 'post')
    def test_missing_homologated_base_blocks_save(self, post, read, scope, allowed):
        result = music_events.api_events(self.request('post', {
            'titulo': 'RT', 'data_evento': '2026-10-19', 'tipo': 'REUNIAO_TECNICA', 'base_id': 'missing',
        }))
        self.assertEqual(result.status_code, 400)
        post.assert_not_called()

    @patch.object(music_events, '_allowed', return_value=True)
    @patch.object(music_events, '_visible_events', return_value=[])
    @patch.object(music_events, '_read')
    def test_detail_outside_scope_does_not_read_participants(self, read, events, allowed):
        self.assertEqual(music_events.api_detail(self.request(), 'other-event').status_code, 404)
        read.assert_not_called()

    @patch.object(music_events, '_allowed', return_value=True)
    @patch.object(music_events, '_visible_events', return_value=[{'id': 'event-1'}])
    @patch.object(music_events, 'user_scope', return_value={'level': 'municipal', 'municipio': 'COTIA'})
    @patch.object(music_events, '_read', return_value=[
        {'comum_codigo': 'BR-22-1', 'comum': 'Comum A', 'municipio': 'COTIA'},
        {'comum_codigo': 'BR-22-2', 'comum': 'Comum B', 'municipio': 'ITAPEVI'},
    ])
    def test_detail_filters_origin_and_hides_cross_territory_totals(self, read, scope, events, allowed):
        result = json.loads(music_events.api_detail(self.request(), 'event-1').content)
        self.assertEqual(len(result['frequency']), 1)
        self.assertEqual(result['frequency'][0]['municipio'], 'COTIA')
        self.assertEqual(result['locations'], [])
        self.assertEqual(read.call_count, 1)


class MusicEventPageSeparationTests(SimpleTestCase):
    @patch.object(music_events, '_read')
    @patch.object(music_events, 'user_scope', return_value={'level': 'regional'})
    def test_category_filters_events_before_dashboard_and_history(self, scope, read):
        read.return_value = [
            {'id': 'rehearsal', 'tipo': 'ENSAIO_REGIONAL'},
            {'id': 'meeting', 'tipo': 'REUNIAO_TECNICA'},
        ]
        for category, expected in [('ENSAIO_REGIONAL', 'rehearsal'), ('REUNIAO_TECNICA', 'meeting')]:
            request = RequestFactory().get('/', {'categoria': category})
            self.assertEqual([e['id'] for e in music_events._visible_events(request)], [expected])

    @patch.object(music_events, '_allowed', return_value=True)
    @patch.object(music_events, 'render')
    def test_routes_render_distinct_categories(self, render, allowed):
        from django.urls import resolve
        for path, category in [('/musica/ensaios-regionais/', 'ENSAIO_REGIONAL'),
                               ('/musica/reunioes-tecnicas/', 'REUNIAO_TECNICA')]:
            match = resolve(path)
            self.assertEqual(match.func.__name__, "page")
            request = RequestFactory().get(path)
            request.session = {'user_profile': {'role_id': 1}}
            music_events.page(request, **match.kwargs)
            self.assertEqual(render.call_args.args[2]['event_category'], category)
