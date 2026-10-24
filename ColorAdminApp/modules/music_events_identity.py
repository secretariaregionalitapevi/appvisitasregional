"""Resolve comuns pelo catálogo; nomes ambíguos nunca recebem código por aproximação."""
import re
from .music_events_import import norm


def normalized_city(value):
    city = norm(value)
    return {'CAUCAIA': 'CAUCAIA DO ALTO', 'PIRAPORA': 'PIRAPORA DO BOM JESUS',
            'VGP': 'VARGEM GRANDE PAULISTA', 'VARGEM GRANDE': 'VARGEM GRANDE PAULISTA', 'FAZENDINHA': 'SANTANA DE PARNAIBA',
            'IRAPEVI': 'ITAPEVI', 'SANTANA': 'SANTANA DE PARNAIBA',
            'SANTAN DE PARNAIBA': 'SANTANA DE PARNAIBA',
            'SANTANA DE APARNAIBA': 'SANTANA DE PARNAIBA'}.get(city, city)


def normalized_name(value):
    name = norm(value)
    name = re.sub(r'\bJD\.?\b', 'JARDIM', name)
    name = re.sub(r'\bPQ\.?\b', 'PARQUE', name)
    name = re.sub(r'\bVL\.?\b', 'VILA', name)
    name = re.sub(r'[^A-Z0-9]+', ' ', name)
    name = re.sub(r'\b(DE|DO|DA|DOS|DAS)\b', ' ', name)
    name = re.sub(r'\b([1-4])$', lambda match: {'1': 'I', '2': 'II', '3': 'III', '4': 'IV'}[match[1]], name)
    return ' '.join(name.split())


ALIASES = {
    'ITAPEVI': {'BELA VISTA BAIXA': 'JARDIM BELA VISTA', 'CARDOSO': 'VILA DOUTOR CARDOSO',
                'ENGENHEIRO CARDOSO': 'VILA DOUTOR CARDOSO', 'JARDIM JOIA': 'JARDIM GIOIA',
                'ITACOLOMY': 'JARDIM ITACOLOMI', 'VILA GIOIA': 'JARDIM GIOIA', 'VILA JOIA': 'JARDIM GIOIA',
                'JARDIM ROSIMEIRE': 'JARDIM ROSEMARY', 'ROSEMEIRE I': 'JARDIM ROSEMARY',
                'JARDIM ROSEMEIRE 2': 'JARDIM ROSEMARY II', 'JARDIM ROSIMEIRE 2': 'JARDIM ROSEMARY II',
                'ROZIMEIRE 1': 'JARDIM ROSEMARY', 'SANTA RITA I': 'JARDIM SANTA RITA'},
    'COTIA': {'SITIO LAJEADO': 'LAGEADO', 'ATOS DE CAUCAIA': 'ALTOS DE CAUCAIA'},
    'JANDIRA': {'CHACARA APARECIDINHA': 'CHACARA NOSSA SENHORA APARECIDINHA',
                'DOROLORES JANDIRAA': 'DOROLES PASCHOALIM', 'INFANTES GARDEN': "INFANT'S GARDEN",
                'JARDIM MAZE': 'JARDIM MASE', 'JD ESTELA MARIS': 'JARDIM STELLA MARIS'},
    'SANTANA DE PARNAIBA': {'JABUTICABEIRA': 'JABOTICABEIRA', 'JABOTICABEIRAS': 'JABOTICABEIRA',
                           'CHACARA SOLAR': 'CHACARA SOLAR II',
                           'COLINAS DE ANHANGUERA II': 'COLINAS DA ANHAGUERA II',
                           'COLINAS DO ANHANGUERA II': 'COLINAS DA ANHAGUERA II'},
    'PIRAPORA DO BOM JESUS': {'PARQUE PAYOL 1': 'PARQUE PAIOL',
                             'PARQUE LARANJEIRAS': 'PARQUE LARANJEIRA II'},
}
NORMALIZED_ALIASES = {city: {normalized_name(source): normalized_name(target) for source, target in aliases.items()}
                      for city, aliases in ALIASES.items()}


class CommonResolver:
    def __init__(self, catalog):
        self.has_catalog=bool(catalog)
        self.by_code={};self.by_name={}
        self.normalized = {}; self.cores = {}
        for row in catalog:
            label=row.get('comum') or ''
            match=re.match(r'^(BR-\d+-\d+)\s*-\s*(.*)',label)
            if not match:continue
            self.by_code[match[1]]=row
            description=norm(match[2]);city=norm(row.get('cidade'))
            names={description}
            if description.endswith(' - '+city):names.add(description[:-(len(city)+3)])
            for name in names:self.by_name.setdefault((city,name),[]).append(row)
            canonical_city = normalized_city(city)
            # Sufixos municipais e pontuação não criam uma segunda comum.
            variants = set(names)
            for city_name in {canonical_city, city, 'CAUCAIA' if canonical_city == 'CAUCAIA DO ALTO' else canonical_city}:
                for name in list(variants):
                    stripped = re.sub(r'\s*(?:-\s*)?' + re.escape(city_name) + r'$', '', name).strip(' -')
                    if stripped:
                        variants.add(stripped)
            if any(normalized_name(name).startswith('CENTRAL ') for name in variants):
                variants.update({'CENTRAL', canonical_city, f'CENTRAL {canonical_city}', f'{canonical_city} CENTRAL', f'{canonical_city} CENTRO'})
            for name in variants:
                key = normalized_name(name)
                self.normalized.setdefault((canonical_city, key), {})[match[1]] = row
                core = re.sub(r'^(JARDIM|VILA|PARQUE|BAIRRO|SITIO|CHACARA|RESIDENCIAL) ', '', key)
                self.cores.setdefault((canonical_city, core), {})[match[1]] = row

    def resolve(self, common, city):
        match=re.match(r'^(BR-\d+-\d+)',norm(common))
        if match and match[1] in self.by_code:return self.by_code[match[1]]
        if match:
            common = re.sub(r'^BR-\d+-\d+\s*-?\s*', '', norm(common))
        city=normalized_city(city);name=norm(common)
        if city == 'CENTRAL' and normalized_city(name) in {key[0] for key in self.normalized}:
            city, name = normalized_city(name), 'CENTRAL'
        # Variações confirmadas pelo administrador, limitadas à comum/cidade indicadas.
        if city=='COTIA' and name in {'LAGEADO','LAJEADO','LANJEADO','LANJADO'}:
            return self.by_code.get('BR-22-2797')
        if city=='COTIA' and name=='PUNHO VELHO':
            return self.by_code.get('BR-22-0416')
        if city in {'CAUCAIA','CAUCAIA DO ALTO'} and name=='NHANBUCA':
            canonical=self.by_code.get('BR-21-1020')
            if canonical and 'NHAMBUCA' in norm(canonical['comum']):return canonical
        matches=self.by_name.get((city,name),[])
        if len(matches) == 1:return matches[0]
        key = normalized_name(name)
        alias = NORMALIZED_ALIASES.get(city, {}).get(key)
        if alias:
            key = normalized_name(alias)
        stripped_key = re.sub(r'\s+' + re.escape(normalized_name(city)) + r'$', '', key)
        def candidates(target_city):
            for candidate_key in dict.fromkeys([key, stripped_key]):
                exact = self.normalized.get((target_city, candidate_key), {})
                if exact:return exact
            for candidate_key in dict.fromkeys([key, stripped_key]):
                core = re.sub(r'^(JARDIM|VILA|PARQUE|BAIRRO|SITIO|CHACARA|RESIDENCIAL) ', '', candidate_key)
                matches = self.cores.get((target_city, core), {})
                if matches:return matches
            return {}
        matches = candidates(city)
        if not matches and city in {'COTIA', 'CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA'}:
            matches = {code: row for other in {'COTIA', 'CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA'}
                       for code, row in candidates(other).items()}
        return next(iter(matches.values())) if len(matches) == 1 else None

    def records(self, rows):
        output=[]
        for original in rows:
            row=dict(original)
            common=row.get('comum_codigo') or row.get('comum_informada') or ''
            canonical=self.resolve(common,row.get('municipio_informado'))
            if canonical:
                row['comum_codigo']=re.match(r'^(BR-\d+-\d+)',canonical['comum']).group(1)
                row['comum_informada']=canonical['comum'];row['municipio_informado']=canonical['cidade']
                row.pop('comum_nao_reconhecida', None)
            elif self.has_catalog:
                row['comum_nao_reconhecida']=True
            output.append(row)
        return output
