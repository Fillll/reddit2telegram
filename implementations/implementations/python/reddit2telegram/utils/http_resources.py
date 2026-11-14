"""Verified TLS shared across connections; media sessions owned by one job."""

from contextlib import contextmanager
import ssl
import threading

import requests
from requests.adapters import HTTPAdapter
import benchmark_metrics


# Requests/urllib3 otherwise parse a separate CA store for every TLS connection.
# This context is fully configured before worker threads use it.
TLS_CONTEXT = ssl.create_default_context(cafile=requests.certs.where())
_LOCAL = threading.local()


class SharedTLSAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        benchmark_metrics.count('http_request_attempts')
        try:
            response = super().send(request, **kwargs)
        except Exception:
            benchmark_metrics.count('http_transport_errors')
            raise
        benchmark_metrics.request_status('http', response.status_code)
        if benchmark_metrics.measuring():
            original = response.iter_content

            def measured_content(*args, **kw):
                for chunk in original(*args, **kw):
                    benchmark_metrics.count('http_response_body_bytes', len(chunk))
                    yield chunk

            response.iter_content = measured_content
        return response

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        host, options = super().build_connection_pool_key_attributes(request, verify, cert)
        if verify is True and cert is None:
            options['ssl_context'] = TLS_CONTEXT
        return host, options

    def cert_verify(self, conn, url, verify, cert):
        super().cert_verify(conn, url, verify, cert)
        if conn.conn_kw.get('ssl_context') is TLS_CONTEXT and verify is True and cert is None:
            # The shared context already contains the verified CA store. Loading
            # it again for each socket defeats reuse and mutates a live context.
            conn.ca_certs = None
            conn.ca_cert_dir = None


def session():
    result = requests.Session()
    adapter = SharedTLSAdapter(pool_connections=4, pool_maxsize=1)
    result.mount('http://', adapter)
    result.mount('https://', adapter)
    return result


def media_session():
    result = getattr(_LOCAL, 'session', None)
    if result is None:
        result = _LOCAL.session = session()
    return result


@contextmanager
def media_job():
    # ContextDecorator recreates this scope for each supply call, including
    # exceptions. No idle sockets survive on long-lived executor threads.
    try:
        yield
    finally:
        current = getattr(_LOCAL, 'session', None)
        if current is not None:
            del _LOCAL.session
            current.close()
