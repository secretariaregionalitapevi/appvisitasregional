from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from ColorAdminApp.modules.sam_member_catalog import normalize_page, fetch_listing, full_catalog
from ColorAdminApp.sam_catalog import parse_catalog, match_local_common


HEADERS = ['', 'Nome', 'Comum Congregação', 'Cargo/Ministério', 'Nível', 'Instrumento', 'Tonalidade']


def row(identity='684274', name='LEVI DOS SANTOS'):
    return [identity, name, 'VILA DAS CHÁCARAS', 'MÚSICO', 'OFICIALIZADO(A)', 'TROMPETE', 'DÓ']


class MemberCatalogTests(SimpleTestCase):
    def test_member_columns_do_not_swap_level_and_instrument(self):
        rows = normalize_page({'data': [row()]}, HEADERS, 'members')
        student = parse_catalog({'rows': rows})[0]
        self.assertEqual(student['source_key'], '684274')
        self.assertEqual(student['instrument'], 'TROMPETE')
        self.assertEqual(student['level'], 'OFICIALIZADO(A)')
        self.assertFalse(student['history_available'])

    def test_members_pagination_covers_all_pages_even_when_server_caps_page_size(self):
        document = '<table id="table-grp"><thead><tr>' + ''.join(f'<th>{h}</th>' for h in HEADERS) + '</tr></thead></table>'
        document += '<script>ajax: {url: "/grp_musical/listagem", type: "POST"}</script>'
        page = Mock()
        page.evaluate.side_effect = [document,
            {'recordsTotal': 2, 'recordsFiltered': 2, 'data': [row()]},
            {'recordsTotal': 2, 'recordsFiltered': 2, 'data': [row('500655', 'LEVI DOS SANTOS ALVES')]}]
        session = SimpleNamespace(scraper=SimpleNamespace(page=page), module=SimpleNamespace(config=SimpleNamespace(SITE_URL='https://sam.example/')))
        data = fetch_listing(session, 'grp_musical', 'members')
        self.assertEqual(data['total'], 2)
        self.assertEqual(page.evaluate.call_args_list[-1].args[1]['start'], 1)
        page.evaluate.side_effect = [document, {'recordsTotal': 2, 'data': [row()]}, {'recordsTotal': 2, 'data': [row()]}]
        with self.assertRaisesRegex(ValueError, 'repetida'):
            fetch_listing(session, 'grp_musical', 'members')

    @patch('ColorAdminApp.modules.sam_member_catalog.fetch_listing')
    def test_union_preserves_members_not_present_in_students_and_uses_current_common(self, fetch):
        student = {'cells': ['684274', 'LEVI DOS SANTOS', 'JARDIM SANTA RITA | BR-SP-ITAPEVI-ITAPEVI', 'MÚSICO', 'TROMPETE', 'OFICIALIZADO(A)'], 'history_available': True}
        member = normalize_page({'data': [row(), row('500655', 'LEVI DOS SANTOS ALVES')]}, HEADERS, 'members')
        fetch.side_effect = [{'rows': [student], 'total': 1}, {'rows': member, 'total': 2}]
        result = full_catalog(Mock())
        self.assertEqual(result['total'], 2)
        levi = next(r for r in parse_catalog(result) if r['source_key'] == '684274')
        self.assertEqual(levi['common_name'], 'VILA DAS CHÁCARAS')
        self.assertTrue(levi['history_available'])

    def test_member_common_without_city_requires_unique_regional_match(self):
        catalog = [{'comum': 'BR-22-2999 - VILA DAS CHÁCARAS', 'cidade': 'ITAPEVI'}]
        self.assertEqual(match_local_common({'common_name': 'VILA DAS CHÁCARAS'}, catalog), catalog[0])
        self.assertIsNone(match_local_common({'common_name': 'VILA DAS CHÁCARAS'}, [*catalog,
            {'comum': 'BR-22-9999 - VILA DAS CHÁCARAS', 'cidade': 'JANDIRA'}]))

    def test_shared_student_label_is_not_part_of_person_name(self):
        original = row()
        original[1] += ' (compartilhado)'
        self.assertEqual(normalize_page({'data': [original]}, HEADERS, 'students')[0]['cells'][1], 'LEVI DOS SANTOS')

    def test_wrong_source_counter_requires_independent_matching_census(self):
        document = '<table id="table-grp"><thead><tr>' + ''.join(f'<th>{h}</th>' for h in HEADERS) + '</tr></thead></table>'
        document += '<script>ajax: {url: "/alunos/listagem", type: "POST"}</script>'
        data = {'recordsTotal': 1, 'recordsFiltered': 2,
                'data': [row(), row('500655', 'LEVI DOS SANTOS ALVES')]}
        page = Mock()
        page.evaluate.side_effect = [document, data, data]
        session = SimpleNamespace(scraper=SimpleNamespace(page=page), module=SimpleNamespace(config=SimpleNamespace(SITE_URL='https://sam.example/')))
        captured = fetch_listing(session, 'alunos', 'students', page_size=2)
        self.assertEqual(captured['total'], 2)
        self.assertTrue(captured['counter_discrepancy'])
        self.assertEqual(page.evaluate.call_args_list[-1].args[1]['length'], 10000)
        page.evaluate.side_effect = [document, data, {'data': [row()]}]
        with self.assertRaisesRegex(ValueError, 'divergem'):
            fetch_listing(session, 'alunos', 'students', page_size=2)
