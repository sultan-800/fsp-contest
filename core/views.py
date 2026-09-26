import calendar as pycal
from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from competitions.models import Competition, Result, Submission

from .files import serve_private
from .models import FAQ, Discipline, Document, News, Notification

MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь",
          "Октябрь", "Ноябрь", "Декабрь"]


def home(request):
    User = get_user_model()
    base = Competition.objects.visible().select_related("discipline", "level").annotate(
        _participants_count=Count("registrations", distinct=True))
    running = list(base.running().order_by("end_at")[:3])
    upcoming = list(base.upcoming().order_by("start_at")[:4])
    finished = list(base.finished().filter(results_published=True).order_by("-end_at")[:3])
    for c in finished:
        c.podium = list(c.results.select_related("athlete").order_by("place")[:3])
    top = list(User.objects.filter(role=User.Role.ATHLETE, is_active=True, rating__gt=0)
               .select_related("qualification").order_by("-rating")[:5])
    stats = {
        "athletes": User.objects.filter(role=User.Role.ATHLETE, is_active=True).count(),
        "competitions": Competition.objects.visible().count(),
        "submissions": Submission.objects.count(),
        "disciplines": Discipline.objects.filter(is_active=True).count(),
    }
    news = News.objects.filter(is_published=True, published_at__lte=timezone.now())[:3]
    featured = running[0] if running else (upcoming[0] if upcoming else None)
    return render(request, "core/home.html", {
        "featured": featured, "running": running, "upcoming": upcoming, "finished": finished,
        "top": top, "stats": stats, "news": news,
        "disciplines": Discipline.objects.filter(is_active=True),
    })


# Инфоцентр
def info_index(request):
    now = timezone.now()
    return render(request, "core/info/index.html", {
        "news": News.objects.filter(is_published=True, published_at__lte=now)[:4],
        "docs": Document.objects.filter(is_published=True, category__in=[Document.Category.REGULATION, Document.Category.RULES])[:6],
        "materials": Document.objects.filter(is_published=True, category=Document.Category.MATERIAL)[:4],
        "faq": FAQ.objects.filter(is_published=True)[:5],
        "next_events": Competition.objects.visible().filter(end_at__gt=now).order_by("start_at")[:5],
        "section": "index",
    })


def news_list(request):
    qs = News.objects.filter(is_published=True, published_at__lte=timezone.now())
    tag = request.GET.get("tag", "")[:40]
    if tag:
        qs = qs.filter(tag=tag)
    page = Paginator(qs, 9).get_page(request.GET.get("page"))
    tags = News.objects.filter(is_published=True).values_list("tag", flat=True).distinct()
    return render(request, "core/info/news_list.html", {"page": page, "tags": sorted(set(tags)), "tag": tag, "section": "news"})


def news_detail(request, pk):
    item = get_object_or_404(News, pk=pk, is_published=True)
    more = News.objects.filter(is_published=True).exclude(pk=pk)[:3]
    return render(request, "core/info/news_detail.html", {"item": item, "more": more, "section": "news"})


def calendar_view(request):
    today = timezone.localdate()
    try:
        y, m = map(int, request.GET.get("month", "").split("-"))
        cur = date(y, m, 1)
    except (ValueError, TypeError):
        cur = today.replace(day=1)
    if not (2000 <= cur.year <= 2100):
        cur = today.replace(day=1)
    weeks = pycal.Calendar(firstweekday=0).monthdatescalendar(cur.year, cur.month)
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(weeks[0][0], time.min), tz)
    end = timezone.make_aware(datetime.combine(weeks[-1][-1], time.max), tz)
    comps = list(Competition.objects.visible().filter(start_at__lte=end, end_at__gte=start)
                 .select_related("discipline", "level").order_by("start_at"))
    grid = []
    for week in weeks:
        row = []
        for d in week:
            day_events = [c for c in comps
                          if timezone.localtime(c.start_at).date() <= d <= timezone.localtime(c.end_at).date()]
            row.append({"date": d, "in_month": d.month == cur.month, "today": d == today, "events": day_events})
        grid.append(row)
    prev_m = (cur - timedelta(days=1)).replace(day=1)
    next_m = (cur + timedelta(days=32)).replace(day=1)
    month_events = [c for c in comps if timezone.localtime(c.start_at).month == cur.month
                    or timezone.localtime(c.end_at).month == cur.month]
    return render(request, "core/info/calendar.html", {
        "grid": grid, "cur": cur, "month_name": MONTHS[cur.month - 1], "prev": prev_m, "next": next_m,
        "events": month_events, "weekdays": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], "section": "calendar",
    })


def documents(request):
    cat = request.GET.get("cat", "")
    qs = Document.objects.filter(is_published=True)
    if cat in Document.Category.values:
        qs = qs.filter(category=cat)
    groups = []
    for value, label in Document.Category.choices:
        items = [d for d in qs if d.category == value]
        if items:
            groups.append({"key": value, "label": label, "items": items})
    return render(request, "core/info/documents.html", {
        "groups": groups, "cat": cat, "categories": Document.Category.choices, "section": "documents"})


def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk, is_published=True)
    return render(request, "core/info/document_detail.html", {"doc": doc, "section": "documents"})


def document_download(request, pk):
    doc = get_object_or_404(Document, pk=pk, is_published=True)
    if not doc.file:
        raise Http404
    return serve_private(doc.file, f"{doc.title[:80]}.{doc.file_ext.lower()}", inline=True)


def faq(request):
    items = FAQ.objects.filter(is_published=True)
    groups = {}
    for i in items:
        groups.setdefault(i.category, []).append(i)
    return render(request, "core/info/faq.html", {"groups": groups, "section": "faq"})



# уведомления
@login_required
def notifications(request):
    items = request.user.notifications.all()[:60]
    return render(request, "core/notifications.html", {"items": items})


@login_required
@require_POST
def notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("core:notifications")


@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.is_read = True
    n.save(update_fields=["is_read"])
    if n.url and url_has_allowed_host_and_scheme(n.url, allowed_hosts={request.get_host()}):
        return redirect(n.url)
    return redirect("core:notifications")


def privacy(request):
    return render(request, "core/privacy.html")


# ошибки
def _err(request, code, title, text):
    return render(request, "error.html", {"code": code, "title": title, "text": text}, status=code)


def error_400(request, exception=None):
    return _err(request, 400, "Некорректный запрос", "Сервер не смог обработать запрос.")


def error_403(request, exception=None):
    return _err(request, 403, "Доступ запрещён", "У вас нет прав для просмотра этой страницы.")


def error_404(request, exception=None):
    return _err(request, 404, "Страница не найдена", "Возможно, она была удалена или вы ошиблись адресом.")


def error_500(request):
    return render(request, "error.html", {"code": 500, "title": "Ошибка сервера",
                                          "text": "Что-то пошло не так. Мы уже разбираемся."}, status=500)
