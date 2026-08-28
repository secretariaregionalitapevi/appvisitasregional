import importlib
import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Lê diretamente do SAM as tabelas históricas de um aluno, sem gravar dados."

    def add_arguments(self, parser):
        parser.add_argument("student")
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
            scraper = module.MusicalScraper(debug_stages=True)
            if not scraper.login() or not scraper.navigate_to_students() or not scraper.search_student(options["student"]):
                raise CommandError("Não foi possível abrir o histórico do aluno no SAM.")
            result = {"student": options["student"], "tabs": {}}
            for tab_name in ("MSA", "Método", "Hinário", "Provas", "Escalas"):
                try:
                    container = scraper._activate_history_tab(tab_name)
                except Exception as exc:
                    result["tabs"][tab_name] = {"error": str(exc), "tables": []}
                    continue
                tables = []
                for table in container.locator("table").all():
                    tables.append(table.evaluate("""table => {
                        const headers = [...table.querySelectorAll('thead th')].map(x => x.innerText.trim());
                        const rows = [...table.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
                        let previous = [], node = table.previousElementSibling, count = 0;
                        while (node && count < 4) { previous.unshift((node.innerText || '').trim()); node = node.previousElementSibling; count++; }
                        return {headers, rows, context: previous.filter(Boolean).join(' | ')};
                    }"""))
                result["tabs"][tab_name] = {"tables": tables}
            output = options["output"].resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Estrutura salva em {output}"))
        finally:
            if scraper:
                scraper.close()
