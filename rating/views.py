from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from core.models import CompetitionLevel, Discipline, Qualification

from . import services


def rating_view(request):
    User = get_user_model()
    disc = request.GET.get("discipline", "")
    discipline = Discipline.objects.filter(pk=int(disc)).first() if disc.isdigit() else None
    city = request.GET.get("city", "").strip()[:80]
    q = request.GET.get("q", "").strip()[:80]
    qual = request.GET.get("qualification", "")

    data = services.compute_athlete_values(discipline=discipline)
    rows = sorted(data.values(), key=lambda d: (-d["value"], d["athlete"].last_name))
    # Позиции считаются до фильтрации — чтобы место в общем рейтинге не менялось от поиска
    prev, pos = None, 0
    ranked = []
    for i, d in enumerate(rows, 1):
        if d["value"] <= 0:
            continue
        if d["value"] != prev:
            pos = i
        prev = d["value"]
        d["position"] = pos
        ranked.append(d)

    def match(d):
        a = d["athlete"]
        if city and city.lower() not in a.city.lower():
            return False
        if q and q.lower() not in a.full_name.lower():
            return False
        if qual.isdigit() and a.qualification_id != int(qual):
            return False
        return True

    filtered = [d for d in ranked if match(d)]
    filtering = bool(city or q or qual.isdigit())
    podium = ranked[:3] if not filtering else []
    page = Paginator(filtered if filtering else ranked[3:] if len(ranked) > 3 else [], 30).get_page(request.GET.get("page"))
    cities = sorted({d["athlete"].city for d in ranked if d["athlete"].city})
    return render(request, "rating/index.html", {
        "podium": podium, "page": page, "filtering": filtering, "discipline": discipline,
        "disciplines": Discipline.objects.filter(is_active=True), "qualifications": Qualification.objects.all(),
        "levels": CompetitionLevel.objects.all(), "cities": cities, "total": len(ranked),
        "f": {"discipline": disc, "city": city, "q": q, "qualification": qual},
        "half_life": services.HALF_LIFE_DAYS,
    })
