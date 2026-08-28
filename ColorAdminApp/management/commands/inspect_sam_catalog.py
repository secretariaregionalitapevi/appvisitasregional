import importlib
import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Lê o catálogo completo de alunos diretamente do SAM, sem gravar no Supabase."

    def add_arguments(self, parser):
        parser.add_argument("--scraper-dir", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)

    def handle(self, *args, **options):
        scraper_dir = options["scraper_dir"].resolve()
        if not (scraper_dir / "web_scraper.py").is_file():
            raise CommandError("Projeto do scraper SAM não encontrado.")
        sys.path.insert(0, str(scraper_dir))
        scraper = None
        try:
            module = importlib.import_module("web_scraper")
            scraper = module.MusicalScraper(debug_stages=False)
            if not scraper.login() or not scraper.navigate_to_students():
                raise CommandError("Não foi possível abrir o catálogo de alunos no SAM.")
            if not scraper._wait_for_students_datatable():
                raise CommandError("A tabela de alunos do SAM não foi inicializada.")
            try:
                scraper.page.wait_for_function("""() => {
                    const table = jQuery('#table-grp').DataTable();
                    const info = table.page.info();
                    return info.recordsTotal > 0 || !table.processing();
                }""", timeout=30000)
            except Exception:
                pass
            scraper.page.wait_for_timeout(1500)
            result = scraper.page.evaluate("""async () => {
                const table = jQuery('#table-grp').DataTable();
                const headers = [...document.querySelectorAll('#table-grp thead th')]
                    .map(th => (th.innerText || '').trim());
                const params = {...(table.ajax.params() || {})};
                params.start = 0;
                params.length = table.page.info().recordsDisplay || table.page.info().recordsTotal || 10000;
                const query = new URLSearchParams(params);
                const response = await fetch(table.ajax.url() + '?' + query.toString(), {
                    credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}
                });
                if (!response.ok) throw new Error(`Falha HTTP ${response.status} ao ler catálogo`);
                const payload = await response.json();
                const raw = payload.data || payload.aaData || [];
                const rows = raw.map((item, index) => {
                    if (Array.isArray(item)) return {index, cells: item.map(value => String(value ?? ''))};
                    if (item && typeof item === 'object') return {index, data: item};
                    return {index, cells: [String(item ?? '')]};
                });
                return {
                    headers, rows, total: payload.recordsTotal ?? payload.iTotalRecords ?? table.page.info().recordsTotal,
                    page_info: table.page.info(),
                    ajax_url: table.ajax && table.ajax.url ? table.ajax.url() : null,
                    resources: performance.getEntriesByType('resource')
                        .map(item => item.name).filter(name => /aluno|gem|datatable/i.test(name))
                };
            }""")
            output = options["output"].resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(
                f"Catálogo SAM lido: {len(result.get('rows') or [])}/{result.get('total') or 0} registros em {output}"
            ))
        finally:
            if scraper:
                scraper.close()
