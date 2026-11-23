from datetime import datetime
from unittest.mock import patch
from django.test import SimpleTestCase
from ColorAdminApp.modules.regional_agenda_google import normalize_events, presentation
from ColorAdminApp.modules import regional_agenda as api


class GoogleMirrorTests(SimpleTestCase):
    def event(self, **changes):
        return {'id':'google-id','summary':'Ensaio existente','location':'Central',
                'start':{'dateTime':'2026-11-23T19:00:00-03:00'},
                'end':{'dateTime':'2026-11-23T21:00:00-03:00'},**changes}

    def test_identity_is_stable_and_scoped_to_google_calendar(self):
        first=normalize_events([self.event()],'calendar-a')[0]
        self.assertEqual(first['id'],normalize_events([self.event()],'calendar-a')[0]['id'])
        self.assertNotEqual(first['id'],normalize_events([self.event()],'calendar-b')[0]['id'])

    def test_all_day_uses_sao_paulo_and_exclusive_end(self):
        row=normalize_events([self.event(start={'date':'2026-11-23'},end={'date':'2026-11-24'})],'cal')[0]
        self.assertTrue(row['dia_inteiro']);self.assertTrue(row['inicio'].endswith('-03:00'))
        self.assertEqual((datetime.fromisoformat(row['fim'])-datetime.fromisoformat(row['inicio'])).days,1)

    def test_canceled_is_removed_and_transparent_is_visible_as_available(self):
        self.assertEqual(normalize_events([self.event(status='cancelled')],'cal'),[])
        row=normalize_events([self.event(transparency='transparent')],'cal')[0]
        self.assertTrue(row['disponivel']);self.assertEqual(presentation(row)['status'],'GOOGLE_DISPONIVEL')

    def test_malformed_or_duplicate_snapshot_is_not_treated_as_empty(self):
        for events in ([self.event(),self.event()],[self.event(end={})],None):
            with self.assertRaises((ValueError,KeyError)):normalize_events(events,'cal')

    def test_google_record_is_read_only_and_has_no_approval(self):
        event=presentation(normalize_events([self.event()],'cal')[0])
        self.assertTrue(event['somente_leitura']);self.assertIsNone(event['criado_por'])
        self.assertEqual(event['conflitos'],[]);self.assertEqual(event['status'],'GOOGLE')

    @patch.object(api,'rpc',side_effect=api.AgendaError('Aplique 066_agenda_leitura_google.sql',503))
    def test_missing_migration_is_an_explicit_diagnostic(self,_rpc):
        from datetime import date
        rows,status=api.google_window(date(2026,11,1),date(2026,12,1))
        self.assertEqual(rows,[]);self.assertFalse(status['instalada']);self.assertIn('066',status['mensagem'])
