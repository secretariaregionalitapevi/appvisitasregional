"""Verifica a inicialização separadamente das dependências opcionais de upload."""
import os
import subprocess
import sys
from pathlib import Path
from django.test import SimpleTestCase


class DeploymentStartupTests(SimpleTestCase):
    def test_url_loading_does_not_import_pdf_upload_parser(self):
        code = '''
import os, sys, importlib.abc
os.environ['DJANGO_SETTINGS_MODULE'] = 'ColorAdmin.settings'
class BlockUploadParser(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'pypdf' or fullname.startswith('pypdf.'):
            raise ModuleNotFoundError("No module named 'pypdf'")
sys.meta_path.insert(0, BlockUploadParser())
import django
django.setup()
from django.urls import get_resolver, resolve
assert get_resolver().url_patterns
assert resolve('/darpe/documentos/').url_name == 'darpeDocumentos'
assert resolve('/user/login-v1').url_name
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[2], env=dict(os.environ), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
