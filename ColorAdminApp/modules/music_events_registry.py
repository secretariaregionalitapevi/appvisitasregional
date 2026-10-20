"""Referência do cadastro local existente, sem simular captura histórica SAM."""
from collections import Counter
from .music_events_identity import CommonResolver
from .music_events_dashboard import code, event_kind
from .music_events_import import norm


def instrument_family(instrument):
    value=norm(instrument)
    if value in {'VIOLINO','VIOLA','VIOLONCELO','ACORDEON'}:return 'CORDAS'
    if any(x in value for x in ['FLAUT','OBO','CLARIN','FAGOT','SAXOF']):return 'MADEIRAS'
    if any(x in value for x in ['TROMP','CORNET','FLUGEL','BARIT','EUPH','EUFO','TUBA','SAX HORN']):return 'METAIS'
    return 'OUTROS'


def attach_registry(data, people, catalog):
    resolver=CommonResolver(catalog);counts=Counter();seen=set();dates=[]
    for row in people:
        identity=str(row.get('id') or '')
        if not identity or identity in seen:continue
        seen.add(identity)
        if norm(row.get('status')) not in {'ATIVO','ALERTA','CONCLUIDO'}:continue
        inst=row.get('instrumento') or ''
        if not inst or norm(inst)=='A DEFINIR':continue
        common=resolver.resolve(row.get('comum_congregacao'),row.get('municipio'))
        if not common:continue
        category='ORGANISTA' if norm(inst)=='ORGAO' else 'MUSICO'
        counts[(code(common['comum']),category,instrument_family(inst))]+=1
        if row.get('updated_at'):dates.append(str(row['updated_at']))
    kinds={event_kind(e) for e in data['events']}
    family=next(iter(kinds)).removeprefix('RT_') if len(kinds)==1 else 'GERAL'
    for row in data['rows']:
        key=code(row['comum'])
        # Ausência de cadastro reconhecido é desconhecida, não zero.
        known=any(k[0]==key for k in counts)
        for category,field in [('MUSICO','cadastro_musicos'),('ORGANISTA','cadastro_organistas')]:
            row[field]=sum(v for (c,cat,f),v in counts.items() if c==key and cat==category
                          and (family not in {'CORDAS','MADEIRAS','METAIS'} or cat=='MUSICO' and f==family)) if known else None
    data['registry']={'available':bool(counts),'updated_at':max(dates) if dates else None,
                      'criterion':'Cadastro local atual: status Ativo, Alerta e Concluido; todos os níveis, inclusive oficializados. Inativos e Excluir fora da referência. Não é captura histórica.'}
    return data
