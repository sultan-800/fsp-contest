import json

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from competitions.models import Competition, Registration, Result, Submission

from . import throttle
from .forms import DeleteAccountForm, LoginForm, PrivacyForm, ProfileForm, RegistrationForm
from .models import User


def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return nxt
    return default


@sensitive_post_parameters("password1", "password2")
@csrf_protect
@never_cache
def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
        messages.success(request, f"Добро пожаловать, {user.first_name}! Профиль спортсмена создан.")
        return redirect(_safe_next(request, "accounts:profile"))
    return render(request, "accounts/register.html", {"form": form})


@sensitive_post_parameters("password")
@csrf_protect
@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = LoginForm(request, data=request.POST or None)
    locked = False
    if request.method == "POST":
        username = request.POST.get("username", "")
        if throttle.is_locked(request, username):
            locked = True
            form = LoginForm(request)
            messages.error(request, "Слишком много неудачных попыток. Повторите через 15 минут.")
        elif form.is_valid():
            throttle.reset(request, username)
            user = form.get_user()
            request.session.cycle_key()
            login(request, user)
            messages.success(request, f"Вы вошли как {user.display_name}")
            default = "panel:dashboard" if user.is_organizer else "accounts:profile"
            return redirect(_safe_next(request, default))
        else:
            throttle.register_failure(request, username)
    return render(request, "accounts/login.html", {"form": form, "locked": locked,
                                                   "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "Вы вышли из аккаунта")
    return redirect("core:home")


def _athlete_context(athlete):
    results = (Result.objects.filter(athlete=athlete, competition__results_published=True)
               .select_related("competition__discipline", "competition__level").order_by("-competition__end_at"))
    history = list(athlete.rating_history.all())
    stats = {
        "competitions": results.count(),
        "wins": results.filter(place=1).count(),
        "podiums": results.filter(place__lte=3).count(),
        "best": min((r.place for r in results), default=None),
        "points": sum(r.rating_points for r in results),
    }
    return {"athlete": athlete, "results": results, "history": history[-24:],
            "history_values": [h.value for h in history[-24:]], "stats": stats}


@login_required
def profile(request):
    user = request.user
    tab = request.GET.get("tab", "overview")
    if tab not in {"overview", "competitions", "contests"}:
        tab = "overview"
    ctx = _athlete_context(user)
    regs = (Registration.objects.filter(athlete=user)
            .select_related("competition__discipline", "competition__level")
            .annotate(subs=Count("competition__submissions", filter=Q(competition__submissions__athlete=user)))
            .order_by("-competition__start_at"))
    now = timezone.now()
    active = [r for r in regs if r.competition.is_published and r.competition.end_at > now]
    past = [r for r in regs if r.competition.end_at <= now]
    my_results = {r.competition_id: r for r in Result.objects.filter(athlete=user)}
    for r in past:
        r.my_result = my_results.get(r.competition_id)
    subs = (Submission.objects.filter(athlete=user).select_related("task", "competition")
            .order_by("-created_at")[:50])
    recommended = []
    if user.is_athlete:
        recommended = (Competition.objects.visible().filter(end_at__gt=now)
                       .exclude(registrations__athlete=user).select_related("discipline", "level")
                       .order_by("start_at")[:3])
    ctx.update({"tab": tab, "active_regs": active, "past_regs": past, "submissions": subs,
                "recommended": recommended, "is_own": True})
    return render(request, "accounts/profile.html", ctx)


def athlete_detail(request, pk):
    athlete = get_object_or_404(User, pk=pk, is_active=True, role=User.Role.ATHLETE)
    if request.user.is_authenticated and request.user.pk == athlete.pk:
        return redirect("accounts:profile")
    ctx = _athlete_context(athlete)
    viewer_is_org = request.user.is_authenticated and request.user.is_organizer
    ctx["limited"] = not athlete.is_profile_public and not viewer_is_org
    ctx["viewer_is_org"] = viewer_is_org
    return render(request, "accounts/athlete.html", ctx)


@sensitive_post_parameters("old_password", "new_password1", "new_password2", "password")
@login_required
@never_cache
def settings_view(request):
    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None
    profile_form = ProfileForm(request.POST if action == "profile" else None, instance=user, prefix="p")
    privacy_form = PrivacyForm(request.POST if action == "privacy" else None, instance=user, prefix="v")
    password_form = PasswordChangeForm(user, request.POST if action == "password" else None, prefix="s")
    delete_form = DeleteAccountForm(user, request.POST if action == "delete" else None, prefix="d")

    if action == "profile" and profile_form.is_valid():
        profile_form.save()
        messages.success(request, "Профиль обновлён")
        return redirect("accounts:settings")
    if action == "privacy" and privacy_form.is_valid():
        privacy_form.save()
        messages.success(request, "Настройки приватности сохранены")
        return redirect("accounts:settings")
    if action == "password" and password_form.is_valid():
        password_form.save()
        update_session_auth_hash(request, password_form.user)
        messages.success(request, "Пароль изменён")
        return redirect("accounts:settings")
    if action == "delete" and delete_form.is_valid():
        if user.is_organizer and User.objects.filter(role=User.Role.ORGANIZER, is_active=True).count() <= 1:
            messages.error(request, "Нельзя удалить единственного организатора")
            return redirect("accounts:settings")
        _anonymize(user)
        logout(request)
        messages.info(request, "Аккаунт удалён, персональные данные стёрты")
        return redirect("core:home")
    return render(request, "accounts/settings.html", {
        "profile_form": profile_form, "privacy_form": privacy_form,
        "password_form": password_form, "delete_form": delete_form,
        "active": action or request.GET.get("section", "profile"),
    })


def _anonymize(user):
    uid = user.pk
    user.username = f"deleted_{uid}"
    user.email = f"deleted_{uid}@deleted.invalid"
    user.first_name, user.last_name, user.middle_name = "Удалённый", "Участник", ""
    user.city = user.institution = user.bio = ""
    user.birth_date = None
    user.is_active = False
    user.is_profile_public = False
    user.set_unusable_password()
    user.save()
    user.disciplines.clear()
    user.notifications.all().delete()


@login_required
def export_data(request):
    u = request.user
    data = {
        "account": {"username": u.username, "email": u.email, "role": u.get_role_display(),
                    "date_joined": u.date_joined.isoformat(), "consent_at": u.consent_at.isoformat() if u.consent_at else None},
        "profile": {"last_name": u.last_name, "first_name": u.first_name, "middle_name": u.middle_name,
                    "birth_date": u.birth_date.isoformat() if u.birth_date else None, "city": u.city,
                    "institution": u.institution, "qualification": str(u.qualification or ""),
                    "qualification_verified": u.qualification_verified,
                    "disciplines": [d.name for d in u.disciplines.all()], "bio": u.bio},
        "rating": {"value": u.rating, "position": u.rating_position,
                   "history": [{"date": h.created_at.isoformat(), "value": h.value, "reason": h.reason}
                               for h in u.rating_history.all()]},
        "registrations": [{"competition": r.competition.title, "date": r.created_at.isoformat()}
                          for r in u.registrations.select_related("competition")],
        "results": [{"competition": r.competition.title, "place": r.place, "score": r.score,
                     "rating_points": r.rating_points} for r in u.results.select_related("competition")],
        "submissions": [{"id": s.pk, "task": str(s.task), "competition": s.competition.title,
                         "language": s.get_language_display(), "created_at": s.created_at.isoformat(),
                         "score": s.score, "comment": s.comment}
                        for s in u.submissions.select_related("task", "competition")],
    }
    resp = HttpResponse(json.dumps(data, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="fsp-contest-data-{u.pk}.json"'
    return resp
