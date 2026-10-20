"""Compatibilidade dos imports após a reorganização em modules."""
from pathlib import Path

_modules_dir = str(Path(__file__).resolve().parent / "modules")
if _modules_dir not in __path__:
    __path__.append(_modules_dir)
