"""Ограничение попыток входа (защита от перебора паролей)."""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger("security")


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _keys(request, username):
    u = hashlib.sha256((username or "").lower().strip().encode()).hexdigest()[:24]
    return [f"login:ip:{client_ip(request)}", f"login:user:{u}"]


def is_locked(request, username):
    return any(cache.get(k, 0) >= settings.LOGIN_MAX_ATTEMPTS * (3 if "ip" in k else 1) for k in _keys(request, username))


def register_failure(request, username):
    for k in _keys(request, username):
        try:
            cache.incr(k)
        except ValueError:
            cache.set(k, 1, settings.LOGIN_LOCKOUT_SECONDS)
    log.warning("Неудачная попытка входа с %s", client_ip(request))


def reset(request, username):
    cache.delete_many(_keys(request, username))
