from pathlib import Path
import re

path = Path('static/js/admin/auditoria.js')
source = path.read_text(encoding='utf-8')
source, count = re.subn(r'try\{(await fetchJsonWithTimeout\([^;]+;)(await fetchJsonWithTimeout\([^;]+;)',
                       r'try{\2\1', source)
assert count == 1
path.write_text(source, encoding='utf-8')
