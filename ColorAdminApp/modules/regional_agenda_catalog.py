"""Agendas municipais e sua administração responsável (sem credenciais)."""
CALENDARS = (
    {'id': 'cotia', 'administracao_id': 'cotia', 'nome': 'Cotia', 'municipio': 'Cotia'},
    {'id': 'caucaia', 'administracao_id': 'cotia', 'nome': 'Caucaia do Alto', 'municipio': 'Caucaia do Alto'},
    {'id': 'vargem_grande', 'administracao_id': 'cotia', 'nome': 'Vargem Grande Paulista', 'municipio': 'Vargem Grande Paulista'},
    {'id': 'itapevi', 'administracao_id': 'itapevi', 'nome': 'Itapevi', 'municipio': 'Itapevi'},
    {'id': 'jandira', 'administracao_id': 'jandira', 'nome': 'Jandira', 'municipio': 'Jandira'},
    {'id': 'santana', 'administracao_id': 'santana', 'nome': 'Santana de Parnaíba', 'municipio': 'Santana de Parnaíba'},
    {'id': 'pirapora', 'administracao_id': 'santana', 'nome': 'Pirapora do Bom Jesus', 'municipio': 'Pirapora do Bom Jesus'},
)
CALENDAR_BY_ID = {row['id']: row for row in CALENDARS}
