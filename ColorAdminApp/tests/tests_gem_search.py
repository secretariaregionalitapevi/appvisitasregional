from django.test import SimpleTestCase
from ColorAdminApp.modules.gem_search import database_filter, matches, terms


class GemSearchTests(SimpleTestCase):
    def test_partial_names_accept_middle_surname_and_sousa_variant(self):
        student = {'nome_aluno': 'ALCIDES COELHO DE SOUZA'}
        for query in ('Alcides Sousa', 'Alcides Souza', 'Sousa Alcides', 'Alcides Coelho'):
            self.assertTrue(matches(student, query))
        self.assertFalse(matches({'nome_aluno': 'ALCIDES COELHO DA SILVA'}, 'Alcides Sousa'))

    def test_database_query_requires_all_words_and_contains_both_spellings(self):
        query = database_filter('Alcides Sousa')
        self.assertIn('nome_aluno.ilike.*Alcides*', query)
        self.assertIn('),or(', query)
        self.assertIn('nome_aluno.ilike.*SOUSA*', query)
        self.assertIn('nome_aluno.ilike.*SOUZA*', query)

    def test_punctuation_cannot_inject_database_filters(self):
        self.assertEqual(terms('Alcides*,()._% Sousa'), ['Alcides', 'Sousa'])
