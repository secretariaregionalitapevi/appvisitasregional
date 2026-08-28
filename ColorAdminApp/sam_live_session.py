import importlib
import sys
from pathlib import Path


class SamLiveSession:
    """Uma sessão autenticada e invisível para catálogo e múltiplos históricos."""

    def __init__(self, scraper_dir, headless=True):
        scraper_dir = Path(scraper_dir).resolve()
        if str(scraper_dir) not in sys.path:
            sys.path.insert(0, str(scraper_dir))
        module = importlib.import_module("web_scraper")
        module.config.SELENIUM_HEADLESS = headless
        self.module = module
        self.scraper = module.MusicalScraper(debug_stages=False)
        if headless:
            old_page = self.scraper.page
            self.scraper.page = self.scraper.browser.new_page(
                viewport={"width": 1600, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/139.0.0.0 Safari/537.36"
                ),
            )
            self.scraper.page.set_default_timeout(60000)
            self.scraper._configure_page_optimizations()
            old_page.close()

    def _open_students(self):
        if "painel" not in self.scraper.page.url.lower():
            url = self.module.config.SITE_URL.rstrip("/") + "/painel"
            self.scraper.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            self.scraper.page.wait_for_function("() => !!window.jQuery", timeout=20000)
            gem_menu = self.scraper.page.locator("li.treeview:has-text('G.E.M')").first
            if "active" not in (gem_menu.get_attribute("class") or ""):
                gem_menu.click(force=True, timeout=10000)
            alunos_link = self.scraper.page.locator("li.treeview.active a[href='alunos']").first
            alunos_link.click(force=True, timeout=10000)
            self.scraper.page.wait_for_selector("#table-grp", state="attached", timeout=20000)
            self.scraper._students_page_ready = self.scraper._wait_for_students_datatable()
        except Exception as exc:
            self.scraper._students_page_ready = False
            print(
                "[DIAGNÓSTICO SAM] lista indisponível:",
                {"url": self.scraper.page.url, "title": self.scraper.page.title(), "table_count": self.scraper.page.locator("#table-grp").count(), "error": str(exc)},
            )
        if not self.scraper._students_page_ready:
            state = self.scraper.page.evaluate("""() => ({
                jquery: !!window.jQuery,
                dataTable: !!(window.jQuery && jQuery.fn && jQuery.fn.DataTable),
                initialized: !!(window.jQuery && jQuery.fn && jQuery.fn.DataTable && jQuery.fn.DataTable.isDataTable('#table-grp')),
                rows: document.querySelectorAll('#table-grp tbody tr').length
            })""")
            print("[DIAGNÓSTICO SAM] tabela não inicializada:", state)
        return self.scraper._students_page_ready

    def start(self):
        if not self.scraper.login() or not self._open_students():
            raise RuntimeError("Não foi possível iniciar a sessão autenticada no SAM.")

    def recover(self):
        if not self.scraper.reconnect() or not self._open_students():
            raise RuntimeError("Não foi possível recuperar a sessão do SAM.")

    def catalog(self):
        if not self._open_students() or not self.scraper._wait_for_students_datatable():
            self.recover()
        try:
            self.scraper.page.wait_for_function("""() => {
                const table = jQuery('#table-grp').DataTable();
                return table.page.info().recordsTotal > 0;
            }""", timeout=30000)
        except Exception:
            pass
        self.scraper.page.wait_for_timeout(1000)
        return self.scraper.page.evaluate("""async () => {
            const table = jQuery('#table-grp').DataTable();
            const headers = [...document.querySelectorAll('#table-grp thead th')].map(th => (th.innerText || '').trim());
            const params = {...(table.ajax.params() || {})};
            params.start = 0;
            params.length = table.page.info().recordsDisplay || table.page.info().recordsTotal || 10000;
            const response = await fetch(table.ajax.url() + '?' + new URLSearchParams(params).toString(), {
                credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            if (!response.ok) throw new Error(`Falha HTTP ${response.status} ao ler catálogo`);
            const payload = await response.json();
            const raw = payload.data || payload.aaData || [];
            const rows = raw.map((item, index) => Array.isArray(item)
                ? {index, cells: item.map(value => String(value ?? ''))}
                : {index, data: item});
            return {headers, rows, total: payload.recordsTotal ?? payload.iTotalRecords ?? rows.length};
        }""")

    def history(self, student):
        for attempt in range(2):
            if self._open_students() and self.scraper.search_student(student):
                try:
                    return self._extract_open_history(student)
                finally:
                    self._open_students()
            if attempt == 0:
                self.recover()
        raise RuntimeError(f"Não foi possível abrir o histórico de {student} no SAM.")

    def _extract_open_history(self, student):
        result = {"student": student, "tabs": {}}
        for tab_name in ("MSA", "M\u00e9todo", "Hin\u00e1rio", "Provas", "Escalas"):
            try:
                container = self.scraper._activate_history_tab(tab_name)
            except Exception as exc:
                result["tabs"][tab_name] = {"error": str(exc), "tables": []}
                continue
            tables = []
            for table in container.locator("table").all():
                tables.append(table.evaluate("""table => {
                    const headers = [...table.querySelectorAll('thead th')].map(x => x.innerText.trim());
                    const rows = [...table.querySelectorAll('tbody tr')]
                        .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
                    let previous = [], node = table.previousElementSibling, count = 0;
                    while (node && count < 4) {
                        previous.unshift((node.innerText || '').trim()); node = node.previousElementSibling; count++;
                    }
                    return {headers, rows, context: previous.filter(Boolean).join(' | ')};
                }"""))
            result["tabs"][tab_name] = {"tables": tables}
        return result

    def close(self):
        self.scraper.close()
