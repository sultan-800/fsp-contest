import math

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import RatingHistory

HALF_LIFE_DAYS = 365


def size_coefficient(n):
    return 1 + 0.25 * math.log10(max(n, 1))


def field_coefficient(athletes):
    pts = [a.qualification.points if (a.qualification and a.qualification_verified) else 0 for a in athletes]
    avg = sum(pts) / len(pts) if pts else 0
    return 1 + min(avg, 300) / 1000


def place_points(place, n):
    n = max(n, 1)
    return 100 * (n - place + 1) / n


def result_points(place, n, level_coef, field_coef):
    return round(place_points(place, n) * float(level_coef) * size_coefficient(n) * field_coef, 2)


def decay_factor(when, now=None):
    now = now or timezone.now()
    age = max(0, (now - when).total_seconds() / 86400)
    return 0.5 ** (age / HALF_LIFE_DAYS)


def qualification_bonus(user):
    if user.qualification_id and user.qualification_verified:
        return user.qualification.points
    return 0


def compute_athlete_values(discipline=None, now=None):
    """Возвращает {athlete_id: {'value', 'q', 'comp', 'count', 'best'}} для всех спортсменов."""
    from competitions.models import Result

    User = get_user_model()
    now = now or timezone.now()
    athletes = User.objects.filter(role=User.Role.ATHLETE, is_active=True).select_related("qualification")
    data = {a.id: {"athlete": a, "q": qualification_bonus(a) if discipline is None else 0,
                   "comp": 0.0, "count": 0, "best": None} for a in athletes}
    results = Result.objects.filter(competition__results_published=True).select_related("competition")
    if discipline is not None:
        results = results.filter(competition__discipline=discipline)
    for r in results:
        d = data.get(r.athlete_id)
        if d is None:
            continue
        d["comp"] += r.rating_points * decay_factor(r.competition.end_at, now)
        d["count"] += 1
        d["best"] = r.place if d["best"] is None else min(d["best"], r.place)
    for d in data.values():
        d["value"] = round(d["q"] + d["comp"], 1)
    return data


@transaction.atomic
def recalculate(reason="Пересчёт рейтинга", competition=None):
    User = get_user_model()
    data = compute_athlete_values()
    ordered = sorted(data.values(), key=lambda d: (-d["value"], d["athlete"].last_name, d["athlete"].id))
    to_update = []
    history = []
    pos = 0
    prev_value = None
    for idx, d in enumerate(ordered, start=1):
        a = d["athlete"]
        value = d["value"]
        if value > 0:
            if value != prev_value:
                pos = idx
            prev_value = value
            position = pos
        else:
            position = None
        changed = abs(a.rating - value) >= 0.05 or a.rating_position != position
        if changed:
            delta = round(value - a.rating, 1)
            if abs(delta) >= 0.05 or not a.rating_history.exists():
                history.append(RatingHistory(athlete=a, value=value, position=position, delta=delta,
                                             reason=reason[:200], competition=competition))
            a.rating = value
            a.rating_position = position
            to_update.append(a)
    if to_update:
        User.objects.bulk_update(to_update, ["rating", "rating_position"])
    if history:
        RatingHistory.objects.bulk_create(history)
    return len(to_update)
