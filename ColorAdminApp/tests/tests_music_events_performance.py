from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from ColorAdminApp.modules import music_events as module


class MusicEventsPerformanceTests(SimpleTestCase):
    def test_reimported_event_uses_latest_version_without_combining_attendance(self):
        original = {'id': 'old', 'titulo': 'Ensaio Regional · 15/11/2026',
                    'data_evento': '2026-11-15', 'tipo': 'ENSAIO_REGIONAL',
                    'familia': 'GERAL', 'created_at': '2026-11-15T14:59:00+00:00'}
        latest = {**original, 'id': 'latest', 'created_at': '2026-11-15T17:00:00+00:00'}
        technical = {**original, 'id': 'technical', 'tipo': 'REUNIAO_TECNICA'}
        other_day = {**original, 'id': 'other-day', 'data_evento': '2026-09-20'}
        other_family = {**technical, 'id': 'strings', 'familia': 'CORDAS'}
        request = RequestFactory().get('/')
        with patch.object(module, '_read', return_value=[original, latest, technical, other_day, other_family]), \
                patch.object(module, 'user_scope', return_value={'level': 'regional'}):
            visible = module._visible_events(request)
        self.assertEqual([event['id'] for event in visible],
                         ['latest', 'technical', 'other-day', 'strings'])
        self.assertEqual(module._latest_event_versions([latest, original]), [latest])

    def setUp(self):
        self.events = [
            {'id': key, 'titulo': key, 'tipo': 'ENSAIO_REGIONAL', 'familia': 'GERAL',
             'status': 'ABERTO', 'data_evento': day, 'base_id': None}
            for key, day in [('old', '2026-05-17'), ('current', '2026-09-20')]
        ]
        self.request = RequestFactory().get('/', {'evento': 'current'})
        self.catalog = [{'comum': 'BR-22-1 - Central', 'cidade': 'ITAPEVI'}]
        self.calls = []

    def read(self, table, **params):
        self.calls.append((table, params))
        ids = params.get('evento_id', '')
        events = [event for event in self.events if event['id'] in ids]
        if table == 'musica_evento_presencas':
            return [{'evento_id': event['id'], 'local_id': event['id'] + '-site',
                     'categoria': 'MUSICO', 'comum_codigo': 'BR-22-1',
                     'municipio_informado': 'ITAPEVI', 'familia': 'CORDAS'} for event in events]
        if table == 'musica_evento_locais':
            return [{'id': event['id'] + '-site', 'evento_id': event['id'], 'nome': 'ITAPEVI'} for event in events]
        return []

    def data(self, **kwargs):
        with patch.object(module, '_visible_events', return_value=self.events), \
                patch.object(module, 'user_scope', return_value={'level': 'regional'}), \
                patch.object(module, 'common_catalog', return_value=self.catalog), \
                patch.object(module, '_read', side_effect=self.read), \
                patch.object(module, '_registry', return_value=[]) as registry, \
                patch.object(module, '_leaders', return_value=[]) as leaders:
            result = module.dashboard_data(self.request, **kwargs)
            return result, registry.call_count, leaders.call_count

    def test_initial_dashboard_fetches_only_selected_event(self):
        result, _, _ = self.data(include_history=False)
        self.assertEqual(result['totals']['total'], 1)
        self.assertIsNone(result['evolution'])
        self.assertTrue(self.calls)
        self.assertTrue(all(params['evento_id'] == 'in.(current)' for _, params in self.calls))

    def test_selected_rehearsal_keeps_leader_origins_outside_destination_cycle(self):
        self.catalog.append({'comum': 'BR-22-2 - Cotia', 'cidade': 'COTIA'})
        result, _, _ = self.data(include_history=False)
        self.assertEqual(set(result['filters']['municipios']), {'ITAPEVI', 'PIRAPORA DO BOM JESUS'})
        self.assertEqual([row['city'] for row in result['conductors']['catalog']], ['ITAPEVI', 'COTIA'])

    def test_pirapora_leader_attending_santana_is_in_origin_summary(self):
        self.events[1]['data_evento'] = '2026-11-15'
        self.catalog = [{'comum': 'BR-22-1 - Central', 'cidade': 'PIRAPORA DO BOM JESUS'}]
        original_read = self.read
        def read(table, **params):
            rows = original_read(table, **params)
            for row in rows:
                if table == 'musica_evento_presencas':
                    row.update(municipio_informado='PIRAPORA DO BOM JESUS',
                               nome='Encarregado de Pirapora', cargo='ENCARREGADO LOCAL')
                elif table == 'musica_evento_locais':
                    row['nome'] = 'SANTANA DE PARNAÍBA'
            return rows
        with patch.object(self, 'read', side_effect=read):
            result, _, _ = self.data(include_history=False)
        row = result['conductors']['rows'][0]
        self.assertEqual(row['municipio'], 'PIRAPORA DO BOM JESUS')
        self.assertEqual(row['situacao'], 'PRESENTE')
        self.assertEqual(row['locais_validos'], ['SANTANA DE PARNAÍBA'])
        self.assertEqual(result['conductors']['totals']['PRESENTE'], 1)
        self.request = RequestFactory().get('/', {'evento': 'current', 'municipio': 'COTIA'})
        with patch.object(self, 'read', side_effect=read):
            filtered, _, _ = self.data(include_history=False)
        self.assertEqual(filtered['conductors']['rows'], [])

    def test_explicit_municipality_selection_is_preserved(self):
        self.request = RequestFactory().get('/', {'evento': 'current', 'municipio': ['ITAPEVI', 'PIRAPORA DO BOM JESUS']})
        result, _, _ = self.data(include_history=False)
        self.assertTrue(all(row['municipio'] in {'ITAPEVI', 'PIRAPORA DO BOM JESUS'} for row in result['rows']))
        self.assertTrue(all(row['municipio'] in {'ITAPEVI', 'PIRAPORA DO BOM JESUS'} for row in result['conductors']['rows']))

    def test_history_keeps_comparisons_without_loading_sam_or_reviews(self):
        result, registry_calls, leader_calls = self.data(history_only=True)
        self.assertEqual([point['event_id'] for point in result['evolution']['points']], ['old', 'current'])
        self.assertEqual(registry_calls, 0)
        self.assertEqual(leader_calls, 0)
        self.assertEqual({table for table, _ in self.calls}, {'musica_evento_presencas', 'musica_evento_locais'})

    def test_complete_data_remains_available_for_exports(self):
        result, _, _ = self.data()
        self.assertEqual(result['totals']['total'], 1)
        self.assertEqual(len(result['evolution']['points']), 2)

    def test_initial_request_selects_latest_visible_event(self):
        self.events.reverse()
        self.request = RequestFactory().get('/', {'inicial': '1'})
        result, _, _ = self.data(include_history=False)
        self.assertEqual(result['filters']['evento'], 'current')
        self.assertEqual(result['totals']['total'], 1)

    def test_history_filters_people_by_user_scope(self):
        self.catalog.append({'comum': 'BR-22-2 - Other', 'cidade': 'COTIA'})
        original_read = self.read
        def mixed_read(table, **params):
            rows = original_read(table, **params)
            if table == 'musica_evento_presencas':
                rows += [{**row, 'comum_codigo': 'BR-22-2', 'municipio_informado': 'COTIA'} for row in rows]
            return rows
        with patch.object(module, '_visible_events', return_value=self.events), \
                patch.object(module, 'user_scope', return_value={'level': 'municipal', 'municipio': 'ITAPEVI'}), \
                patch.object(module, 'common_catalog', return_value=self.catalog), \
                patch.object(module, '_read', side_effect=mixed_read):
            result = module.dashboard_data(self.request, history_only=True)
        self.assertEqual([point['total'] for point in result['evolution']['points']], [1, 1])

    @patch.object(module.requests, 'Session')
    def test_paginated_read_reuses_connection_and_does_not_truncate(self, session):
        client = session.return_value.__enter__.return_value
        responses = [Mock(), Mock()]
        for response in responses:
            response.status_code = 200
        responses[0].json.return_value = [{'id': i} for i in range(1000)]
        responses[1].json.return_value = [{'id': 1000}]
        client.get.side_effect = responses
        self.assertEqual(len(module._read('example')), 1001)
        self.assertEqual(session.call_count, 1)
        self.assertEqual([call.kwargs['params']['offset'] for call in client.get.call_args_list], [0, 1000])

    @patch('ColorAdminApp.utils.supabase_http.time.sleep')
    @patch.object(module.requests, 'Session')
    def test_paginated_read_recovers_from_transient_gateway_failure(self, session, _sleep):
        client = session.return_value.__enter__.return_value
        unavailable, recovered = Mock(status_code=503), Mock(status_code=200)
        recovered.json.return_value = [{'id': 'event-1'}]
        client.get.side_effect = [unavailable, recovered]

        self.assertEqual(module._read('example'), [{'id': 'event-1'}])
        self.assertEqual(client.get.call_count, 2)
