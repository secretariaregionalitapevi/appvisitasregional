"""Recuperação limitada de leituras quando a conexão do Supabase cai."""

import time
import logging
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)


def supabase_get(url, *, session=None, **kwargs):
    """Repete somente GET; preserva TLS e nunca repete gravações/exclusões."""
    kwargs.setdefault('timeout', (3.05, 10))
    client = session or requests
    for attempt in range(3):
        try:
            response = client.get(url, **kwargs)
            # Apenas o caminho: filtros, tokens e dados pessoais nao vao ao log.
            logger.info(
                'supabase_read path=%s status=%s response_bytes=%s attempt=%s',
                urlsplit(url).path, response.status_code,
                response.headers.get('Content-Length', 'unknown'), attempt + 1,
            )
            if response.status_code not in {429, 502, 503, 504} or attempt == 2:
                return response
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 2:
                raise
        time.sleep(0.2 * (attempt + 1))
