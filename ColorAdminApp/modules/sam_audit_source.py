"""Leitura isolada da pagina de logs do SAM atraves da sessao autenticada."""
from datetime import date, timedelta

from bs4 import BeautifulSoup


def fetch_audit_logs(session, start=0, length=1000, lookback_days=7):
    base = session.module.config.SITE_URL.rstrip("/")
    errors = []
    candidates = ["/logs", "/log", "/usuarios/logs"]
    try:
        page = session.scraper.page
        page.goto(base + "/painel", wait_until="domcontentloaded", timeout=60000)
        discovered = page.evaluate("""() => {
            const norm = value => String(value || '').normalize('NFD')
                .replace(/[\u0300-\u036f]/g, '').toUpperCase();
            const link = [...document.querySelectorAll('a[href]')].find(a =>
                norm(a.innerText).includes('LOGS DO SISTEMA'));
            return link ? link.getAttribute('href') : null;
        }""")
        if discovered:
            candidates.insert(0, discovered)
    except Exception:
        pass
    for path in candidates:
        try:
            page = session.scraper.page
            target = path if str(path).lower().startswith(("http://", "https://")) else base + "/" + str(path).lstrip("/")
            page.goto(target, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_function("() => !!(window.jQuery && jQuery.fn && jQuery.fn.DataTable)", timeout=15000)
                result = page.evaluate("""async ({start, length}) => {
                const tables = [...document.querySelectorAll('table')];
                const table = tables.find(node => jQuery.fn.DataTable.isDataTable(node));
                if (!table) throw new Error('Tabela de logs nao encontrada');
                const dt = jQuery(table).DataTable();
                const headers = [...table.querySelectorAll('thead th')].map(th => (th.innerText || '').trim());
                const params = {...(dt.ajax.params() || {}), start, length};
                const ajax = dt.ajax.url();
                const response = await fetch(ajax + (ajax.includes('?') ? '&' : '?') + new URLSearchParams(params), {
                    credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const payload = await response.json();
                return {headers, rows: payload.data || payload.aaData || [],
                    total: payload.recordsFiltered ?? payload.recordsTotal ?? payload.iTotalRecords ?? 0};
                }""", {"start": start, "length": length})
            except Exception:
                # A pagina real e um formulario: o relatorio e devolvido por
                # POST e so depois recebe DataTables. Consultamos o mesmo
                # endpoint, preservando a sessao autenticada.
                finish = date.today()
                begin = finish - timedelta(days=max(1, int(lookback_days)))
                document = page.evaluate("""async payload => {
                    const response = await fetch('/logs/buscar_logs', {
                        method: 'POST', credentials: 'same-origin',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                  'X-Requested-With': 'XMLHttpRequest'},
                        body: new URLSearchParams(payload)
                    });
                    const text = await response.text();
                    if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 200)}`);
                    return text;
                }""", {"id_usuario": "0", "acao": "", "data_inicial": begin.strftime("%d/%m/%Y"),
                         "data_final": finish.strftime("%d/%m/%Y")})
                soup = BeautifulSoup(document or "", "html.parser")
                table = next((node for node in soup.select("table") if node.select_one("tbody tr")), None)
                if table is None:
                    raise RuntimeError("O relatorio de logs do SAM nao devolveu registros.")
                headers = [cell.get_text(" ", strip=True) for cell in table.select("thead th")]
                rows = [[cell.get_text(" ", strip=True) for cell in row.select("td")] for row in table.select("tbody tr")]
                result = {"headers": headers, "rows": rows[start:start + length], "total": len(rows)}
            if result is not None:
                return result
        except Exception as exc:
            errors.append(f"{path}: {exc}")
            continue
    raise RuntimeError("A pagina de Logs do Sistema nao foi localizada no SAM. " + " | ".join(errors))
