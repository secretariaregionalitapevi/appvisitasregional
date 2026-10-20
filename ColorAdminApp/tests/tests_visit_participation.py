import json
from unittest.mock import Mock, patch
from django.test import RequestFactory, SimpleTestCase
from ColorAdminApp.utils.visit_participation import regional_team_confirmed
from ColorAdminApp.utils.routing import auto_dispatch_visits
from ColorAdminApp.views import apiVisitasEquipes, visitasRoteiro


class VisitParticipationTests(SimpleTestCase):
    def test_poll_allows_only_confirmed_regional_groups(self):
        for letter in 'ABCDEFGHIJKLM':
            with self.subTest(group=letter):
                self.assertEqual(regional_team_confirmed('Grupo ' + letter, '2026-10-17', 'ITAPEVI'), letter in 'ABEFGHK')

    def test_poll_does_not_disable_other_dates_cities_or_local_teams(self):
        for team, date, city in [('Grupo D', '2026-10-24', 'ITAPEVI'), ('Grupo D', '2026-10-17', 'JANDIRA'), ('Equipe 1', '2026-10-17', 'ITAPEVI'), ('Grupo RF', '2026-10-17', 'ITAPEVI'), ('Grupo RE', '2026-10-17', 'ITAPEVI')]:
            with self.subTest(team=team, date=date, city=city):
                self.assertTrue(regional_team_confirmed(team, date, city))

    @patch('ColorAdminApp.utils.routing.requests.post')
    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_dispatch_never_reads_or_creates_visits_for_unconfirmed_groups(self, get, post):
        for letter in 'CDIJLM':
            self.assertEqual(auto_dispatch_visits('Grupo ' + letter, '2026-10-17', comum='COMUM', cidade='ITAPEVI'), [])
        get.assert_not_called()
        post.assert_not_called()

    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.views.visible_commons', return_value=[{'comum': 'COMUM', 'cidade': 'ITAPEVI'}])
    @patch('ColorAdminApp.views.user_scope', return_value={})
    def test_direct_route_request_is_blocked_before_dispatch(self, scope, commons, get):
        for letter in 'DIJL':
            request = RequestFactory().get('/visitas/roteiro/', {'comum': 'COMUM', 'data': '2026-10-17', 'equipe': 'Grupo ' + letter})
            self.assertEqual(visitasRoteiro(request).status_code, 409)
        get.assert_not_called()

    @patch('ColorAdminApp.views.filter_rows', side_effect=lambda scope, rows: rows)
    @patch('ColorAdminApp.views.requests.get')
    @patch('ColorAdminApp.views.user_scope', return_value={})
    def test_route_catalog_filters_poll_but_regular_catalog_keeps_teams(self, scope, get, filter_rows):
        teams = [{'nome': 'Grupo ' + letter, 'tipo': 'REGIONAL', 'municipio': 'ITAPEVI', 'ativo': True} for letter in 'ABCDEFGHIJKLM']
        get.return_value = Mock(status_code=200, json=lambda: teams)
        request = RequestFactory().get('/visitas/api/equipes/', {'modo': 'catalogo', 'roteiro': 'true', 'data': '2026-10-17'})
        response = apiVisitasEquipes(request)
        self.assertEqual([t['nome'] for t in json.loads(response.content)], ['Grupo ' + letter for letter in 'ABEFGHK'])
        request = RequestFactory().get('/visitas/api/equipes/', {'modo': 'catalogo'})
        self.assertEqual(len(json.loads(apiVisitasEquipes(request).content)), 13)
