"""Resolve comuns pelo catálogo; nomes ambíguos nunca recebem código por aproximação."""
import re
from .music_events_import import norm


class CommonResolver:
    def __init__(self, catalog):
        self.has_catalog=bool(catalog)
        self.by_code={};self.by_name={}
        for row in catalog:
            label=row.get('comum') or ''
            match=re.match(r'^(BR-\d+-\d+)\s*-\s*(.*)',label)
            if not match:continue
            self.by_code[match[1]]=row
            description=norm(match[2]);city=norm(row.get('cidade'))
            names={description}
            if description.endswith(' - '+city):names.add(description[:-(len(city)+3)])
            for name in names:self.by_name.setdefault((city,name),[]).append(row)

    def resolve(self, common, city):
        match=re.match(r'^(BR-\d+-\d+)',norm(common))
        if match:return self.by_code.get(match[1])
        city=norm(city);name=norm(common)
        # Variações confirmadas pelo administrador, limitadas à comum/cidade indicadas.
        if city=='COTIA' and name in {'LAGEADO','LAJEADO','LANJEADO','LANJADO'}:
            return self.by_code.get('BR-22-2797')
        if city=='COTIA' and name=='PUNHO VELHO':
            return self.by_code.get('BR-22-0416')
        if city in {'CAUCAIA','CAUCAIA DO ALTO'} and name=='NHANBUCA':
            canonical=self.by_code.get('BR-21-1020')
            if canonical and 'NHAMBUCA' in norm(canonical['comum']):return canonical
        matches=self.by_name.get((city,name),[])
        return matches[0] if len(matches)==1 else None

    def records(self, rows):
        output=[]
        for original in rows:
            row=dict(original)
            common=row.get('comum_codigo') or row.get('comum_informada') or ''
            canonical=self.resolve(common,row.get('municipio_informado'))
            if canonical:
                row['comum_codigo']=re.match(r'^(BR-\d+-\d+)',canonical['comum']).group(1)
                row['comum_informada']=canonical['comum'];row['municipio_informado']=canonical['cidade']
            elif self.has_catalog:
                row['comum_nao_reconhecida']=True
            output.append(row)
        return output
