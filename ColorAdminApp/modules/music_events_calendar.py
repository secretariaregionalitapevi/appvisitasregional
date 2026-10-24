"""Validação dos destinos de ensaios; não altera o registro original importado."""
from .music_events_identity import normalized_city

FIRST_CIRCUIT = {'ITAPEVI', 'PIRAPORA DO BOM JESUS'}
SECOND_CIRCUIT = {'COTIA', 'CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA', 'JANDIRA', 'SANTANA DE PARNAIBA'}


def regular_destinations(day):
    month = int(str(day)[5:7])
    return FIRST_CIRCUIT if month in {1, 5, 9} else SECOND_CIRCUIT if month in {3, 7, 11} else None


def valid_destination(event, site):
    if not site or site.get('evento_id') != event['id']:
        return False
    allowed = regular_destinations(event['data_evento']) if event.get('tipo') == 'ENSAIO_REGIONAL' else None
    return allowed is None or normalized_city(site.get('municipio') or site.get('nome')) in allowed


def validated_sites(events, sites):
    events = {event['id']: event for event in events}
    return [dict(site, nome='LOCAL A CONFERIR', local_inconsistente=True,
                 nome_original=site.get('nome_original') or site['nome'])
            if site['evento_id'] in events and not valid_destination(events[site['evento_id']], site)
            else dict(site) for site in sites]
