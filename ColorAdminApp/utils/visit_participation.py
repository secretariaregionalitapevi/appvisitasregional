"""Participação regional por data; ausência de voto não confirma presença."""

import re

from django.conf import settings


def regional_team_confirmed(team, visit_date, city):
    name = ' '.join(str(team or '').strip().upper().split())
    if not re.fullmatch(r'GRUPO [A-Z]', name):
        return True  # Equipes locais e RF/RE seguem seu próprio calendário.
    polls = getattr(settings, 'VISITAS_PARTICIPACAO_REGIONAL', {})
    poll = polls.get(str(visit_date or '')[:10])
    if poll is None:
        return True  # Não estender uma enquete a outras datas.
    city_key = str(city or '').strip().upper()
    if not city_key:
        return False  # Não distribuir sem identificar o município da enquete.
    confirmed = poll.get(city_key)
    if confirmed is None:
        return True
    return name in {str(item).strip().upper() for item in confirmed}
