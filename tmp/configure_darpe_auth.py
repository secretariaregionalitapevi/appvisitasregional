"""Configura somente a integracao local autorizada do APP_DARPE."""
from pathlib import Path
import subprocess
import time
import psutil

workspace = Path(__file__).resolve().parents[1]
target = workspace.parent / 'APP_DARPE'
assert target.resolve() == (workspace.parent / 'APP_DARPE').resolve()
assert (target / 'src/server.js').is_file()


def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\'')
    return values


source = read_env(workspace / '.env.local')
for key in ('SUPABASE_URL', 'SUPABASE_ANON_KEY'):
    if not source.get(key):
        raise SystemExit('Configuracao publica ausente no sistema principal: ' + key)
destination = target / '.env'
if destination.exists():
    raise SystemExit('O arquivo .env ja existe. Preservado para revisao.')
values = {'PORT': '3001', 'PRINCIPAL_URL': 'http://127.0.0.1:8000',
          'SUPABASE_URL': source['SUPABASE_URL'], 'SUPABASE_ANON_KEY': source['SUPABASE_ANON_KEY'],
          'APP_ORIGIN': ''}
destination.write_text('\n'.join(key + '=' + value for key, value in values.items()) + '\n',
                       encoding='utf-8', newline='\n')
print('Configuracao local criada; valores de credenciais omitidos.')

listeners = {c.pid for c in psutil.net_connections(kind='tcp')
             if c.status == 'LISTEN' and c.laddr.port == 3001}
for pid in listeners:
    process = psutil.Process(pid)
    if Path(process.cwd()).resolve() != target.resolve() or process.name().lower() != 'node.exe':
        raise SystemExit('Porta 3001 ocupada por outro aplicativo. Nenhum processo encerrado.')
    command = process.cmdline()
    if len(command) != 2 or command[1].replace('\\', '/') != 'src/server.js':
        raise SystemExit('Comando do servidor diverge do esperado. Processo preservado.')
    process.terminate()
    process.wait(timeout=10)
with (target / 'server.log').open('ab') as log:
    server = subprocess.Popen(['node', 'src/server.js'], cwd=target, stdin=subprocess.DEVNULL,
                              stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
print('Servidor APP_DARPE reiniciado. PID:', server.pid)
