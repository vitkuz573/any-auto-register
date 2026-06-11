"""TLS helper utilities."""
from __future__ import annotations

import warnings
from contextlib import contextmanager
from typing import Any

from urllib3.exceptions import InsecureRequestWarning


@contextmanager
def suppress_insecure_request_warning():
    """Suppress urllib3 TLS warnings only when certificate verification is explicitly disabled."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        yield


def insecure_request(request_callable, *args, **kwargs) -> Any:
    """Execute requests with verify=False and suppress corresponding warnings."""
    kwargs.setdefault("verify", False)
    with suppress_insecure_request_warning():
        return request_callable(*args, **kwargs)


def mark_session_insecure(session: Any) -> Any:
    """
    Mark requests.Session as verify=False and use with suppress_insecure_request_warning on the caller side.
    Returns session for chaining.
    """
    session.verify = False
    return session

