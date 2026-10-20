import io
from datetime import datetime
from django.test import SimpleTestCase
from pypdf import PdfReader
from openpyxl import load_workbook
from ColorAdminApp.modules.music_events_dashboard import aggregate
from ColorAdminApp.modules.music_events_conductors import summarize
from ColorAdminApp.modules.music_events_registry import attach_registry
from ColorAdminApp.modules.music_events_reports import build_excel,build_pdf,scope_label


class IdentityAndRegistryTests(SimpleTestCase):
    def fixture(self):
        catalog=[{'comum':'BR-22-2797 - LAGEADO - COTIA','cidade':'COTIA'},
                 {'comum':'BR-22-0416 - MOINHO VELHO','cidade':'COTIA'}]
        events=[{'id':'e','titulo':'Ensaio Regional','data_evento':'2026-09-20','tipo':'ENSAIO_REGIONAL','familia':'GERAL','status':'ABERTO'}]
        sites=[{'id':'l','evento_id':'e','nome':'ITAPEVI'}]
        records=[{'evento_id':'e','local_id':'l','comum_informada':name,'municipio_informado':'COTIA','categoria':'MUSICO','cargo':'ENCARREGADO LOCAL'}
                 for name in ['BR-22-2797 - LAGEADO - COTIA','LAJEADO','LANJEADO','LANJADO']]
        return catalog,events,sites,records

    def test_aliases_consolidate_counts_and_conductor_conferences(self):
        c,e,l,r=self.fixture();d=aggregate(e,r,l,[],{},c)
        self.assertEqual(len(d['rows']),1)
        self.assertEqual(d['rows'][0]['MUSICO'],4)
        self.assertEqual(d['totals']['comuns'],1)
        self.assertEqual(len(summarize(e,r,l,[],{},c)['rows']),1)

    def test_same_name_elsewhere_is_not_merged_and_unknown_is_marked(self):
        c,e,l,r=self.fixture()
        r=[dict(r[0],comum_informada='LAJEADO',municipio_informado='ITAPEVI'),dict(r[0],comum_informada='SEM CADASTRO')]
        d=aggregate(e,r,l,[],{},c)
        self.assertEqual(len(d['rows']),2)
        self.assertTrue(all(x['comum'].startswith('A conferir:') for x in d['rows']))

    def test_confirmed_punho_velho_alias_is_moinho_velho_only_in_cotia(self):
        c,e,l,r=self.fixture()
        r=[dict(r[0],comum_informada='PUNHO VELHO'),dict(r[0],comum_informada='BR-22-0416 - MOINHO VELHO')]
        d=aggregate(e,r,l,[],{},c)
        self.assertEqual(len(d['rows']),1)
        self.assertEqual(d['rows'][0]['comum'],'BR-22-0416 - MOINHO VELHO')
        self.assertEqual(d['rows'][0]['MUSICO'],2)

    def test_registry_all_levels_preserves_history_semantics(self):
        c,e,l,r=self.fixture();d=aggregate(e,r,l,[],{},c)
        people=[{'id':str(i),'status':status,'nivel':level,'instrumento':instrument,'comum_congregacao':'LAGEADO','municipio':'COTIA'}
                for i,(status,level,instrument) in enumerate([('Ativo','CANDIDATO(A)','VIOLINO'),('Concluido','OFICIALIZADO(A)','ÓRGÃO'),('Inativo','RJM','VIOLA'),('Excluir','RJM','TUBA')])]
        attach_registry(d,people+[people[0]],c)
        self.assertEqual(d['rows'][0]['cadastro_musicos'],1)
        self.assertEqual(d['rows'][0]['cadastro_organistas'],1)
        self.assertIsNone(d['rows'][0]['percentual_musicos'])
        self.assertFalse(d['base_complete'])
        book=load_workbook(io.BytesIO(build_excel(d,'Operador',datetime(2026,10,19,12))))
        sheet=book['Frequência por comum']
        self.assertEqual(sheet['G9'].value,'Base SAM atual · músicos')
        self.assertEqual(sheet['G10'].value,1)
        pdf=PdfReader(io.BytesIO(build_pdf(d,'Operador',datetime(2026,10,19,12))))
        text='\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('Base SAM atual',text)
        self.assertNotIn('Base SAM pendente',text)

    def test_export_scope_omits_unused_filters(self):
        c,e,l,r=self.fixture();d=aggregate(e,r,l,[],{'municipios':['COTIA']},c)
        self.assertNotIn('Sem limite',scope_label(d))
        self.assertNotIn('Ano:',scope_label(d))
        self.assertIn('COTIA',scope_label(d))

    def test_nhanbuca_uses_confirmed_nhambuca_catalog_code(self):
        c,e,l,r=self.fixture()
        c.append({'comum':'BR-21-1020 - NHAMBUCA','cidade':'CAUCAIA DO ALTO'})
        r=[dict(r[0],comum_informada=name,municipio_informado='CAUCAIA DO ALTO') for name in ['NHANBUCA','BR-21-1020 - NHAMBUCA']]
        d=aggregate(e,r,l,[],{},c)
        self.assertEqual(len(d['rows']),1)
        self.assertEqual(d['rows'][0]['MUSICO'],2)
