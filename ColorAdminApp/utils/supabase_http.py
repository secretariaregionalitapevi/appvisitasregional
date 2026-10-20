"""Recuperação limitada de leituras quando a conexão do Supabase cai."""

import time

import requests


def supabase_get(url, **kwargs):
    """Repete somente GET; preserva TLS e nunca repete gravações/exclusões."""
    kwargs.setdefault('timeout', (3.05, 10))
    for attempt in range(3):
        try:
            response = requests.get(url, **kwargs)
            if response.status_code not in {429, 502, 503, 504} or attempt == 2:
                return response
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 2:
                raise
        time.sleep(0.2 * (attempt + 1))
