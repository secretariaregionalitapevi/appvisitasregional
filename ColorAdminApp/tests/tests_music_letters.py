import io
from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader
from ColorAdminApp.modules import music_letters
from ColorAdminApp.modules.music_letters_domain import summarize, matches, ministry_workbook, exam_payload
from ColorAdminApp.modules.music_letters_exports import make_pdf, make_excel

def letter(**changes):
    row = {'id': '00000000-0000-4000-8000-000000000001', 'nome': 'CANDIDATO DE EXEMPLO',
           'comum': 'BR-22-2999 - VILA DAS CHÁCARAS', 'municipio': 'ITAPEVI', 'tipo': 'musico',
           'modalidade': 'oficializacao', 'review_result': 'PENDENTE', 'status': 'ready',
           'event_id': 'event', 'event_snapshot': {'data': '2026-11-28', 'evento': 'Avaliação de Músicos (Itapevi)'},
           'payload': {'pessoa_id': '00000000-0000-4000-8000-000000000002', 'instrumento': 'TROMPETE', 'tonalidade': 'SI BEMOL'},
           'ministry_snapshot': {}}
    row.update(changes)
    return row

class MusicLettersTests(SimpleTestCase):
    def test_pending_letters_do_not_count_as_approval(self):
        groups, totals = summarize([letter(), letter(id='second', tipo='organista', modalidade='rjm', review_result='APROVADO')])
        self.assertEqual(totals['cartas'], 2)
        self.assertEqual(totals['aprovados'], 1)
        self.assertEqual(groups[0]['musicos_oficializacao'], 0)
        self.assertEqual(groups[0]['organistas_rjm'], 1)

    def test_four_administrations_are_preserved(self):
        groups, totals = summarize([letter(municipio='Caucaia do Alto', modalidade='culto', review_result='APROVADO'),
                                   letter(municipio='Pirapora do Bom Jesus', review_result='APROVADO')])
        self.assertEqual(groups[2]['musicos_culto_oficial'], 1)
        self.assertEqual(groups[3]['musicos_oficializacao'], 1)

    def test_same_filters_apply_to_exports(self):
        self.assertTrue(matches(letter(), {'municipio': 'ITAPEVI', 'inicio': '2026-11-01', 'fim': '2026-11-30', 'busca': 'candidato exemplo'}))
        self.assertFalse(matches(letter(), {'resultado': 'APROVADO'}))
        self.assertFalse(matches(letter(), {'mes': '10'}))
        self.assertFalse(matches(letter(), {'ano': '2025'}))
        self.assertFalse(matches(letter(), {'comum': 'Outra comum'}))
        self.assertTrue(matches(letter(), {'ano': '2026', 'comum': letter()['comum']}))

    def test_assistance_is_taken_from_source_and_missing_cooperator_has_agreed_text(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['COMUM_ALUNA', 'ID', 'CODIGO_ALUNA', 'ANCIÃO', 'COOPERADOR', 'REGIONAL', 'ENCARREGADO', 'SECRETÁRIO', 'CIDADE'])
        sheet.append(['Central', None, 'BR-21-1039 - CENTRAL', 'ANCIÃO QUE DÁ ASSISTÊNCIA', None, 'REGIONAL', 'LOCAL', 'SECRETÁRIO', 'ITAPEVI'])
        rows = ministry_workbook(workbook, 'source-hash')
        self.assertEqual(rows[0]['anciao'], 'ANCIÃO QUE DÁ ASSISTÊNCIA')
        self.assertEqual(rows[0]['cooperador'], 'Sem Cooperador do Ofício')
        self.assertEqual(rows[0]['source_row'], 2)
        sheet.append(list(next(iter(sheet.values))))
        sheet.append(['Central', None, 'BR-21-1039 - CENTRAL', 'OUTRO', None, 'REGIONAL', 'LOCAL', '', 'ITAPEVI'])
        with self.assertRaises(ValueError):
            ministry_workbook(workbook, 'source-hash')

    def test_confirmation_requires_stable_candidate(self):
        self.assertEqual(exam_payload(letter(), 'Secretário')['tipo_exame'], 'OFICIALIZACAO')
        with self.assertRaises(ValueError):
            exam_payload(letter(payload={}), 'Secretário')

    @patch.object(music_letters, 'can_review', return_value=False)
    def test_confirmation_denies_unprivileged_user_before_database(self, allowed):
        request = RequestFactory().post('/musica/cartas-exames/api/cartas/1/confirmar/', data='{}', content_type='application/json')
        request.session = {}
        with patch.object(music_letters, 'find') as lookup:
            self.assertEqual(music_letters.confirm(request, 'id').status_code, 403)
            lookup.assert_not_called()

    @patch.object(music_letters, 'can_open_module', return_value=False)
    def test_exports_are_not_public(self, allowed):
        request = RequestFactory().get('/musica/cartas-exames/exportar-pdf/')
        request.session = {}
        self.assertEqual(music_letters.export(request, 'pdf').status_code, 403)

    def test_export_pdf_and_excel_have_real_content_and_institutional_header(self):
        rows = [letter(), letter(id='second', nome='OUTRO CANDIDATO', modalidade='culto')]
        pdf = make_pdf(rows, 'Secretário de teste', {'municipio': 'ITAPEVI'})
        reader = PdfReader(io.BytesIO(pdf))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for value in ['CONGREGAÇÃO CRISTÃ NO BRASIL', 'Regional Itapevi', 'CANDIDATO DE EXEMPLO', 'OUTRO CANDIDATO', 'OBSERVAÇÃO']:
            self.assertIn(value, text)
        workbook = load_workbook(io.BytesIO(make_excel(rows, 'Secretário de teste', {})))
        sheet = workbook.active
        self.assertEqual(sheet['A1'].value, 'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertEqual(sheet['A6'].fill.fgColor.rgb[-6:], '1E4B7A')
        self.assertEqual(sheet.freeze_panes, 'A7')
        self.assertEqual(sheet.print_title_rows, '$1:$6')
        self.assertEqual(sheet['H7'].value, '28/11/2026')
        self.assertEqual(sheet.max_row, 8)

    def test_spreadsheet_does_not_execute_user_values_as_formulas(self):
        workbook = load_workbook(io.BytesIO(make_excel([letter(nome='=1+1')], 'Teste', {})))
        self.assertEqual(workbook.active['B7'].data_type, 's')

class MusicLettersActionsTests(SimpleTestCase):
    def request(self, payload=None):
        import json
        request = RequestFactory().post('/actions/', data=json.dumps(payload or {}), content_type='application/json')
        request.session = {'user_id': '00000000-0000-4000-8000-000000000099'}
        return request

    @patch.object(music_letters, 'can_review', return_value=False)
    def test_delete_requires_permission_before_lookup(self, allowed):
        with patch.object(music_letters, 'find') as lookup:
            self.assertEqual(music_letters.delete_letter(self.request(), 'id').status_code, 403)
            lookup.assert_not_called()

    @patch.object(music_letters, 'can_review', return_value=True)
    @patch.object(music_letters, 'find', return_value=None)
    def test_delete_denies_other_scope(self, lookup, allowed):
        with patch.object(music_letters.requests, 'post') as write:
            self.assertEqual(music_letters.delete_letter(self.request(), 'id').status_code, 404)
            write.assert_not_called()

    @patch.object(music_letters, 'can_review', return_value=True)
    @patch.object(music_letters, 'find', return_value=letter())
    @patch.object(music_letters.music_exams, 'actor', return_value='Secretário')
    def test_delete_uses_atomic_rpc_and_expected_version(self, actor, lookup, allowed):
        from unittest.mock import Mock
        response = Mock(status_code=204)
        with patch.object(music_letters.requests, 'post', return_value=response) as write:
            result = music_letters.delete_letter(self.request({'version': 3}), letter()['id'])
            self.assertEqual(result.status_code, 200)
            self.assertTrue(write.call_args.args[0].endswith('/rpc/cartas_excluir'))
            self.assertEqual(write.call_args.kwargs['json']['p_version'], 3)

    @patch.object(music_letters, 'can_open_module', return_value=True)
    @patch.object(music_letters, 'user_scope', return_value={'level': 'municipal'})
    def test_ministry_write_requires_regional_manager(self, scope, allowed):
        with patch.object(music_letters, 'read') as read:
            self.assertEqual(music_letters.manage_ministry(self.request(), 'BR-21-0840').status_code, 403)
            read.assert_not_called()

    @patch.object(music_letters, 'can_open_module', return_value=True)
    @patch.object(music_letters, 'user_scope', return_value={'level': 'global'})
    @patch.object(music_letters, 'can_access', return_value=True)
    @patch.object(music_letters, 'read', return_value=[{'common_code': 'BR-21-0840', 'municipio': 'ITAPEVI', 'comum': 'BR-21-0840 - COMUM'}])
    def test_ministry_rejects_missing_signers(self, read, access, scope, allowed):
        with patch.object(music_letters.requests, 'post') as write:
            self.assertEqual(music_letters.manage_ministry(self.request({'action': 'save', 'version': 1}), 'BR-21-0840').status_code, 400)
            write.assert_not_called()

    def test_conflict_is_reported_without_success(self):
        from unittest.mock import Mock
        response = Mock(status_code=400)
        response.json.return_value = {'message': 'Atualizado por outro usuário'}
        self.assertEqual(music_letters.management_response(response).status_code, 409)

    @patch.object(music_letters, 'read', return_value=[])
    @patch.object(music_letters, 'user_scope', return_value={'level': 'global'})
    def test_deleted_letters_are_not_visible(self, scope, read):
        music_letters.visible(self.request())
        self.assertEqual(read.call_args.args[1]['deleted_at'], 'is.null')
class MusicLetterFilenameTests(SimpleTestCase):
    def test_reference_filename(self):
        from ColorAdminApp.modules.music_letters_domain import letter_filename
        self.assertEqual(letter_filename(letter(nome='EDILSON SOUSA CAMPOS', modalidade='culto', comum='BR-22-0415 - CAPUTERA')),
                         'CARTA CULTO OFICIAL_ EDILSON SOUSA CAMPOS _ BR-22-0415 - CAPUTERA.pdf')

class MinistryMunicipalityTests(SimpleTestCase):
    def test_catalog_code_overrides_imported_administration(self):
        from ColorAdminApp.modules.music_letters_domain import canonical_ministries
        catalog = [
            {'comum': 'BR-21-1019 - ALTOS DE CAUCAIA', 'cidade': 'CAUCAIA DO ALTO'},
            {'comum': 'BR-22-1000 - CENTRAL', 'cidade': 'VARGEM GRANDE PAULISTA'},
        ]
        rows = [dict(common_code=row['comum'][:10], comum=row['comum'], municipio='COTIA') for row in catalog]
        corrected = canonical_ministries(rows, catalog)
        self.assertEqual([r['municipio'] for r in corrected], ['CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA'])
        self.assertTrue(all(r['municipio'] == 'COTIA' for r in rows))

    def test_abbreviated_municipalities_use_existing_aliases(self):
        from ColorAdminApp.modules.music_letters_domain import canonical_ministries
        rows = [{'comum': 'A', 'municipio': 'SANTANA'}, {'comum': 'B', 'municipio': 'PIRAPORA'}]
        self.assertEqual([r['municipio'] for r in canonical_ministries(rows, [])],
                         ['SANTANA DE PARNAIBA', 'PIRAPORA DO BOM JESUS'])

    @patch.object(music_letters, 'user_scope', return_value={'level': 'regional'})
    def test_regional_filter_includes_all_seven_municipalities(self, scope):
        self.assertEqual(len(music_letters.ministry_municipalities(None)), 7)
        self.assertIn('CAUCAIA DO ALTO', music_letters.ministry_municipalities(None))
        self.assertIn('VARGEM GRANDE PAULISTA', music_letters.ministry_municipalities(None))


class MinistryConfirmedLocationTests(SimpleTestCase):
    def test_capela_velha_suru_uses_confirmed_municipality(self):
        from ColorAdminApp.modules.music_letters_domain import canonical_ministries
        for catalog in ([], [{'comum': 'BR-21-1303 - NOME LEGADO', 'cidade': 'COTIA'}]):
            row = canonical_ministries([{'common_code': 'BR-21-1303', 'comum': 'CAPELA VELHA', 'municipio': 'COTIA'}], catalog)[0]
            self.assertEqual(row['comum'], 'BR-21-1303 - CAPELA VELHA - SURU')
            self.assertEqual(row['municipio'], 'SANTANA DE PARNAIBA')
