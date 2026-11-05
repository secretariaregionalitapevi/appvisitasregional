import json
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from ColorAdminApp.modules import darpe_statistics as stats
from ColorAdminApp.tests.tests_darpe_library import request


class DarpeStatisticsTests(SimpleTestCase):
    def payload(self):
        return {'competencia': '2026-10', **dict.fromkeys(stats.METRICS, 10), 'fonte': 'Boletim da administração'}

    def test_validation_requires_integer_values_source_and_valid_period(self):
        for change in [{'unidades': -1}, {'batismos': True}, {'colaboradores': 1.5}, {'pessoas_batizadas': '10'}, {'fonte': ''}, {'competencia': '2026-13'}, {'competencia': '2099-01'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                stats.validate({**self.payload(), **change})

    def test_zero_values_and_period_are_preserved(self):
        data = stats.validate({**self.payload(), 'unidades': 0})
        self.assertEqual(data['unidades'], 0)
        self.assertEqual(data['competencia'], '2026-10-01')

    def test_revisions_select_latest_without_erasing_history(self):
        rows = [{'id': 'first', 'competencia': '2026-10-01', 'created_at': '2026-11-01T10:00:00Z', 'unidades': 220},
                {'id': 'nov', 'competencia': '2026-11-01', 'created_at': '2026-11-03T10:00:00Z', 'unidades': 225},
                {'id': 'revised', 'competencia': '2026-10-01', 'created_at': '2026-11-04T10:00:00Z', 'unidades': 221}]
        self.assertEqual([x['id'] for x in stats.timeline(rows)], ['revised', 'nov'])
        self.assertEqual(rows[0]['unidades'], 220)

    @patch.object(stats, 'allowed', return_value=True)
    @patch.object(stats, 'can_publish', return_value=False)
    @patch.object(stats.requests, 'post')
    def test_local_cannot_publish(self, post, publish, allowed):
        self.assertEqual(stats.api(request('post')).status_code, 403)
        post.assert_not_called()

    def test_anonymous_cannot_read(self):
        req = request(); req.session = {}
        self.assertEqual(stats.api(req).status_code, 403)

    @patch.object(stats, 'allowed', return_value=True)
    @patch.object(stats, 'can_publish', return_value=True)
    @patch.object(stats.requests, 'post')
    def test_publish_appends_and_records_actor(self, post, publish, allowed):
        from django.test import RequestFactory
        req = RequestFactory().post('/darpe/biblioteca/estatisticas/', data=json.dumps(self.payload()), content_type='application/json')
        req.session = request().session
        post.return_value = Mock()
        self.assertEqual(stats.api(req).status_code, 201)
        data = post.call_args.kwargs['json']
        self.assertEqual(data['created_by'], 'gestor')
        self.assertNotIn('id', data)

    @patch.object(stats, 'allowed', return_value=True)
    @patch.object(stats, 'can_publish', return_value=False)
    @patch.object(stats.requests, 'get')
    def test_reader_receives_timeline_and_all_versions(self, get, publish, allowed):
        get.return_value = Mock(json=lambda: [{'id':'a','competencia':'2026-10-01','created_at':'2026-11-01'}, {'id':'b','competencia':'2026-10-01','created_at':'2026-11-02'}])
        response = stats.api(request())
        data = json.loads(response.content)
        self.assertEqual(len(data['versions']), 2)
        self.assertEqual(data['items'][0]['id'], 'b')

    def test_pdf_preserves_families_and_four_sector_columns(self):
        import io
        from pypdf import PdfReader
        from ColorAdminApp.modules.darpe_library_pdf import make_pdf
        pdf = PdfReader(io.BytesIO(make_pdf()))
        self.assertEqual(len(pdf.pages), 1)
        text = pdf.pages[0].extract_text()
        for expected in ['CORDAS', 'MADEIRAS', 'METAIS', 'OBSERVAÇÕES GERAIS', 'SETOR 4']:
            self.assertIn(expected, text)
        self.assertNotIn('SETOR 5', text)
        self.assertNotIn('CONGREGAÇÃO CRISTÃ NO BRASIL', text)
