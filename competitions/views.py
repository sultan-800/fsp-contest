import csv

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import athlete_required
from core.files import serve_private
from core.models import CompetitionLevel, Discipline, Notification

from .forms import SubmissionForm
from .models import Competition, Registration, Result, Submission, Task
from .services import compute_standings


def _get_competition(request, pk):
    comp = get_object_or_404(Competition.objects.select_related("discipline", "level"), pk=pk)
    if not comp.is_published and not (request.user.is_authenticated and request.user.is_organizer):
        raise Http404
    return comp


def _is_org(request):
    return request.user.is_authenticated and request.user.is_organizer


def _registration(request, comp):
    if not request.user.is_authenticated:
        return None
    return Registration.objects.filter(competition=comp, athlete=request.user).first()


def _tasks_visible(request, comp):
    return _is_org(request) or comp.status in (Competition.Status.RUNNING, Competition.Status.FINISHED)


def _my_task_stats(user, comp):
    stats = {}
    if not user.is_authenticated:
        return stats
    for s in Submission.objects.filter(competition=comp, athlete=user).select_related("task"):
        st = stats.setdefault(s.task_id, {"attempts": 0, "best": None, "pending": 0, "last": None})
        st["attempts"] += 1
        if st["last"] is None or s.created_at > st["last"].created_at:
            st["last"] = s
        if s.status == Submission.Status.PENDING:
            st["pending"] += 1
        elif s.score is not None and (st["best"] is None or s.score > st["best"]):
            st["best"] = s.score
    return stats


def competition_list(request):
    qs = (Competition.objects.visible().select_related("discipline", "level")
          .annotate(_participants_count=Count("registrations", distinct=True)))
    status = request.GET.get("status", "")
    if status in {"published", "running", "finished"}:
        qs = qs.with_status(status)
    disc = request.GET.get("discipline", "")
    if disc.isdigit():
        qs = qs.filter(discipline_id=int(disc))
    level = request.GET.get("level", "")
    if level.isdigit():
        qs = qs.filter(level_id=int(level))
    fmt = request.GET.get("format", "")
    if fmt in Competition.Format.values:
        qs = qs.filter(format=fmt)
    q = request.GET.get("q", "").strip()[:100]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q))
    now = timezone.now()
    running = [c for c in qs if c.start_at <= now < c.end_at]
    upcoming = sorted([c for c in qs if c.start_at > now], key=lambda c: c.start_at)
    finished = [c for c in qs if c.end_at <= now]
    my_ids = set()
    if request.user.is_authenticated:
        my_ids = set(Registration.objects.filter(athlete=request.user).values_list("competition_id", flat=True))
    counts = {
        "all": Competition.objects.visible().count(),
        "running": Competition.objects.running().count(),
        "published": Competition.objects.upcoming().count(),
        "finished": Competition.objects.finished().count(),
    }
    return render(request, "competitions/list.html", {
        "running": running, "upcoming": upcoming, "finished": finished, "total": len(running) + len(upcoming) + len(finished),
        "disciplines": Discipline.objects.filter(is_active=True), "levels": CompetitionLevel.objects.all(),
        "formats": Competition.Format.choices, "f": {"status": status, "discipline": disc, "level": level, "format": fmt, "q": q},
        "my_ids": my_ids, "counts": counts,
    })


def competition_detail(request, pk):
    comp = _get_competition(request, pk)
    reg = _registration(request, comp)
    tasks = list(comp.tasks.all()) if _tasks_visible(request, comp) else []
    reg_open, reg_reason = comp.registration_state()
    my_stats = _my_task_stats(request.user, comp) if reg else {}
    for t in tasks:
        t.my = my_stats.get(t.id)

    standings_tasks, standings, standings_mode = [], [], None
    results = []
    if comp.results_published:
        results = list(comp.results.select_related("athlete__qualification").order_by("place", "-score"))
        standings_mode = "final"
        if comp.has_contest:
            standings_tasks, standings = compute_standings(comp)
    elif comp.has_contest and (comp.is_running and comp.show_live_standings or comp.is_finished or _is_org(request)):
        if comp.status != Competition.Status.DRAFT and comp.status != Competition.Status.PUBLISHED:
            standings_tasks, standings = compute_standings(comp)
            standings_mode = "live" if comp.is_running else "pending"

    my_result = None
    if request.user.is_authenticated and comp.results_published:
        my_result = next((r for r in results if r.athlete_id == request.user.id), None)

    my_total = sum((s["best"] or 0) for s in my_stats.values())
    return render(request, "competitions/detail.html", {
        "c": comp, "reg": reg, "tasks": tasks, "reg_open": reg_open, "reg_reason": reg_reason,
        "standings": standings, "standings_tasks": standings_tasks, "standings_mode": standings_mode,
        "results": results, "my_result": my_result, "my_total": my_total,
        "participants": comp.registrations.count(), "is_org": _is_org(request),
        "total_max": sum(t.max_score for t in comp.tasks.all()),
        "tasks_count": comp.tasks.count(),
        "recent_subs": (Submission.objects.filter(competition=comp, athlete=request.user)
                        .select_related("task")[:10] if reg else []),
    })


@require_POST
@athlete_required
def register(request, pk):
    comp = _get_competition(request, pk)
    ok, reason = comp.registration_state()
    if not ok:
        messages.error(request, reason)
    else:
        _, created = Registration.objects.get_or_create(competition=comp, athlete=request.user)
        if created:
            messages.success(request, f"Заявка на «{comp.title}» принята")
            Notification.send(request.user, f"Вы зарегистрированы на «{comp.title}»", comp.get_absolute_url(), "reg")
    return redirect(comp.get_absolute_url())


@require_POST
@athlete_required
def unregister(request, pk):
    comp = _get_competition(request, pk)
    if comp.start_at <= timezone.now():
        messages.error(request, "После старта отменить участие нельзя")
    else:
        Registration.objects.filter(competition=comp, athlete=request.user).delete()
        messages.info(request, "Заявка отозвана")
    return redirect(comp.get_absolute_url())


def task_view(request, pk, letter):
    comp = _get_competition(request, pk)
    if not comp.has_contest:
        raise Http404
    if not _tasks_visible(request, comp):
        messages.info(request, "Задания станут доступны после старта соревнования")
        return redirect(comp.get_absolute_url())
    tasks = list(comp.tasks.all())
    task = next((t for t in tasks if t.letter == letter.upper()), None)
    if task is None:
        raise Http404
    reg = _registration(request, comp)
    my_stats = _my_task_stats(request.user, comp) if reg else {}
    for t in tasks:
        t.my = my_stats.get(t.id)
    my_subs = (Submission.objects.filter(task=task, athlete=request.user).order_by("-created_at")
               if reg else Submission.objects.none())
    attempts_used = my_subs.count() if reg else 0
    can_submit, why = _can_submit(request, comp, reg, attempts_used)
    form = SubmissionForm()
    idx = tasks.index(task)
    return render(request, "competitions/task.html", {
        "c": comp, "task": task, "tasks": tasks, "reg": reg, "form": form, "my_subs": my_subs,
        "can_submit": can_submit, "why": why, "attempts_used": attempts_used,
        "prev_task": tasks[idx - 1] if idx > 0 else None,
        "next_task": tasks[idx + 1] if idx + 1 < len(tasks) else None,
        "my_total": sum((s["best"] or 0) for s in my_stats.values()),
        "total_max": sum(t.max_score for t in tasks),
        "max_kb": settings.SUBMISSION_MAX_FILE_SIZE // 1024,
    })


def _can_submit(request, comp, reg, attempts_used):
    if not request.user.is_authenticated:
        return False, "Войдите, чтобы отправлять решения"
    if not request.user.is_athlete:
        return False, "Организатор не может отправлять решения"
    if not reg:
        return False, "Вы не зарегистрированы на это соревнование"
    if comp.status == Competition.Status.PUBLISHED:
        return False, "Соревнование ещё не началось"
    if comp.status == Competition.Status.FINISHED:
        return False, "Соревнование завершено — приём решений закрыт"
    if attempts_used >= comp.max_attempts:
        return False, f"Исчерпан лимит попыток ({comp.max_attempts})"
    return True, ""


@require_POST
@athlete_required
def submit(request, pk, letter):
    comp = _get_competition(request, pk)
    task = get_object_or_404(Task, competition=comp, letter=letter.upper())
    reg = _registration(request, comp)
    attempts_used = Submission.objects.filter(task=task, athlete=request.user).count()
    ok, why = _can_submit(request, comp, reg, attempts_used)
    if not ok:
        messages.error(request, why)
        return redirect(task.get_absolute_url())
    last = Submission.objects.filter(athlete=request.user, competition=comp).order_by("-created_at").first()
    if last and (timezone.now() - last.created_at).total_seconds() < settings.SUBMISSION_COOLDOWN_SECONDS:
        messages.warning(request, f"Подождите {settings.SUBMISSION_COOLDOWN_SECONDS} секунд между отправками")
        return redirect(task.get_absolute_url())
    form = SubmissionForm(request.POST, request.FILES)
    if form.is_valid():
        sub = form.save(commit=False)
        sub.task, sub.competition, sub.athlete = task, comp, request.user
        sub.save()
        messages.success(request, f"Решение #{sub.pk} по задаче {task.letter} отправлено на проверку")
    else:
        for err in form.errors.values():
            messages.error(request, " ".join(err))
    return redirect(task.get_absolute_url() + "#history")


def task_attachment(request, pk, letter):
    comp = _get_competition(request, pk)
    task = get_object_or_404(Task, competition=comp, letter=letter.upper())
    if not _tasks_visible(request, comp):
        raise Http404
    return serve_private(task.attachment, task.attachment_name or None, inline=True)


def _get_own_submission(request, sid):
    if not request.user.is_authenticated:
        raise PermissionDenied
    sub = get_object_or_404(Submission.objects.select_related("task", "competition", "athlete", "reviewed_by"), pk=sid)
    if sub.athlete_id != request.user.id and not request.user.is_organizer:
        raise Http404  # не раскрываем существование чужих решений
    return sub


@login_required
def submission_detail(request, sid):
    sub = _get_own_submission(request, sid)
    return render(request, "competitions/submission.html", {"s": sub})


@login_required
def submission_download(request, sid):
    sub = _get_own_submission(request, sid)
    if sub.file:
        return serve_private(sub.file, sub.original_filename)
    resp = HttpResponse(sub.code, content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="submission-{sub.pk}.txt"'
    return resp


def results_csv(request, pk):
    comp = _get_competition(request, pk)
    if not comp.results_published and not _is_org(request):
        raise Http404
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="results-{comp.pk}.csv"'
    resp.write("﻿")
    w = csv.writer(resp, delimiter=";")
    tasks = list(comp.tasks.all())
    w.writerow(["Место", "ФИО", "Город", "Разряд", "Баллы", "Штраф (мин)"] + [t.letter for t in tasks] + ["Рейтинговые очки"])
    for r in comp.results.select_related("athlete__qualification").order_by("place"):
        a = r.athlete
        row = [r.place, a.full_name, a.city, a.qualification.short if a.qualification else "", f"{r.score:g}", r.penalty]
        row += [r.details.get(t.letter, "") for t in tasks]
        row.append(f"{r.rating_points:g}")
        w.writerow([_csv_safe(x) for x in row])
    return resp


def _csv_safe(v):
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not s.lstrip("-").replace(".", "").isdigit() else s


def protocol(request, pk):
    comp = _get_competition(request, pk)
    if not comp.results_published and not _is_org(request):
        raise Http404
    results = comp.results.select_related("athlete__qualification").order_by("place")
    return render(request, "competitions/protocol.html", {"c": comp, "results": results, "tasks": comp.tasks.all(),
                                                          "now": timezone.now()})
