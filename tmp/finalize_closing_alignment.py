from pathlib import Path

p=Path('ColorAdminApp/modules/music_events_closing.py')
t=p.read_text(encoding='utf-8').replace("nominal['musicians']", "nominal.get('musicians')").replace("nominal['organists']", "nominal.get('organists')")
p.write_bytes(t.encode('utf-8'))
p=Path('ColorAdminApp/modules/music_events_summary.py')
t=p.read_text(encoding='utf-8').replace("official = closing if closing and closing.get('declared') else None", "official = closing if closing and closing.get('use_as_official_closing') else None")
p.write_bytes(t.encode('utf-8'))
p=Path('ColorAdminApp/modules/music_events_annual_reports.py')
t=p.read_text(encoding='utf-8').replace("(data.get('comparison') or {}).get('current', {}).get('by_municipality', [])", "((data.get('comparison') or {}).get('current') or {}).get('by_municipality', [])")
marker='    return [heading, Spacer(1, 4)'
i=t.index(marker)
note='''    if closing and closing.get('declared') and closing.get('nominal_musicians') is not None:
        reconciliation = ('LISTA NOMINAL DO LOCAL: ' + str(closing['nominal_musicians']) + ' MÚSICOS, '
            + str(closing['nominal_organists']) + ' ORGANISTAS, ' + str(closing['nominal_total']) + ' PESSOAS. '
            + 'DIVERGÊNCIAS DE CLASSIFICAÇÃO E COBERTURA PERMANECEM PARA CONCILIAÇÃO; '
            + 'O FECHAMENTO OFICIAL NÃO ALTERA AS PRESENÇAS POR COMUM.')
        source_note = para('FONTE: ' + closing['source_label'] + '. ' + reconciliation,
                          ParagraphStyle('closing-reconciliation', parent=STYLE, fontSize=8, leading=10))
'''
if "closing-reconciliation" not in t:
    t=t[:i]+note+t[i:]
p.write_bytes(t.encode('utf-8'))
