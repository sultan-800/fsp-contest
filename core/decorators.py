from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def organizer_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_organizer:
            raise PermissionDenied("Раздел доступен только организатору")
        return view(request, *args, **kwargs)
    return wrapper


def athlete_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_athlete:
            raise PermissionDenied("Действие доступно только спортсменам")
        return view(request, *args, **kwargs)
    return wrapper
