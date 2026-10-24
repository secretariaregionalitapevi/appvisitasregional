from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from ColorAdminApp.modules import music_events as module


class MusicEventsPerformanceTests(SimpleTestCase):
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
        responses[0].json.return_value = [{'id': i} for i in range(1000)]
        responses[1].json.return_value = [{'id': 1000}]
        client.get.side_effect = responses
        self.assertEqual(len(module._read('example')), 1001)
        self.assertEqual(session.call_count, 1)
        self.assertEqual([call.kwargs['params']['offset'] for call in client.get.call_args_list], [0, 1000])
