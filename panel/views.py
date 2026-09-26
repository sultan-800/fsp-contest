from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from competitions.models import Competition, Registration, Result, Submission, Task
from competitions.services import assign_places, compute_standings, publish_results, unpublish_results
from core.decorators import organizer_required
from core.models import FAQ, CompetitionLevel, Discipline, Document, News, Notification, Qualification
from rating import services as rating

from . import forms

User = get_user_model()


# ================================================================== дашборд
@organizer_required
def dashboard(request):
    pending = Submission.objects.filter(status=Submission.Status.PENDING)
    now = timezone.now()
    return render(request, "panel/dashboard.html", {
        "pending_count": pending.count(),
        "pending": pending.select_related("athlete", "task", "competition").order_by("created_at")[:8],
        "running": Competition.objects.running().annotate(n=Count("registrations")),
        "upcoming": Competition.objects.upcoming().annotate(n=Count("registrations")).order_by("start_at")[:5],
        "drafts": Competition.objects.filter(is_published=False).order_by("-updated_at")[:5],
        "awaiting_results": Competition.objects.finished().filter(results_published=False),
        "unverified": User.objects.filter(role=User.Role.ATHLETE, is_active=True, qualification__isnull=False,
                                          qualification_verified=False, qualification__points__gt=0).count(),
        "stats": {
            "athletes": User.objects.filter(role=User.Role.ATHLETE, is_active=True).count(),
            "new_athletes": User.objects.filter(role=User.Role.ATHLETE, date_joined__gte=now - timedelta(days=7)).count(),
            "competitions": Competition.objects.count(),
            "submissions": Submission.objects.count(),
            "submissions_today": Submission.objects.filter(created_at__gte=now - timedelta(days=1)).count(),
            "registrations": Registration.objects.count(),
        },
        "nav": "dashboard",
    })


# ================================================================== соревнования
@organizer_required
def competitions(request):
    qs = Competition.objects.select_related("discipline", "level").annotate(
        n=Count("registrations", distinct=True),
        pending=Count("submissions", filter=Q(submissions__status="pending"), distinct=True),
        ntasks=Count("tasks", distinct=True))
    status = request.GET.get("status", "")
    if status in Competition.Status.values:
        qs = qs.with_status(status)
    q = request.GET.get("q", "").strip()[:100]
    if q:
        qs = qs.filter(title__icontains=q)
    return render(request, "panel/competitions.html", {"items": qs, "status": status, "q": q,
                                                       "statuses": Competition.Status.choices, "nav": "competitions"})


@organizer_required
def competition_edit(request, pk=None):
    comp = get_object_or_404(Competition, pk=pk) if pk else None
    initial = {}
    if comp is None:
        start = (timezone.localtime() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        initial = {"start_at": start, "end_at": start + timedelta(hours=4), "location": "Онлайн, платформа ФСП Контест",
                   "rules": DEFAULT_RULES}
    form = forms.CompetitionForm(request.POST or None, instance=comp, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if comp is None:
            obj.created_by = request.user
        obj.save()
        messages.success(request, "Соревнование сохранено" if comp else "Соревнование создано как черновик. Добавьте задания и опубликуйте.")
        return redirect("panel:competition", pk=obj.pk, ) if comp else redirect(reverse("panel:competition", args=[obj.pk]) + "?tab=tasks")
    return render(request, "panel/competition_form.html", {"form": form, "c": comp, "nav": "competitions"})


DEFAULT_RULES = """## Общие положения
- Соревнование проводится в личном зачёте.
- Решения принимаются только в период проведения тура.
- Каждое решение проверяется организатором вручную.

## Отправка решений
- Решение можно ввести в редакторе или загрузить файлом (до 256 КБ).
- По каждой задаче засчитывается лучшая попытка.

## Подведение итогов
- Места распределяются по сумме баллов.
- При равенстве баллов выше тот, кто быстрее набрал свой результат (суммарное время).
- Запрещено использовать чужие решения и передавать своё решение другим участникам."""


@organizer_required
def competition_manage(request, pk):
    comp = get_object_or_404(Competition.objects.select_related("discipline", "level"), pk=pk)
    tab = request.GET.get("tab", "overview")
    if tab not in {"overview", "tasks", "participants", "submissions", "results"}:
        tab = "overview"
    tasks = list(comp.tasks.annotate(nsubs=Count("submissions"),
                                     npending=Count("submissions", filter=Q(submissions__status="pending"))))
    regs = comp.registrations.select_related("athlete__qualification").annotate(
        nsubs=Count("athlete__submissions", filter=Q(athlete__submissions__competition=comp)))
    subs = comp.submissions.select_related("athlete", "task")
    sfilter = request.GET.get("s", "")
    if sfilter in Submission.Status.values:
        subs = subs.filter(status=sfilter)
    pending_count = comp.submissions.filter(status="pending").count()
    standings_tasks, standings = compute_standings(comp) if comp.has_contest else ([], [])
    results = comp.results.select_related("athlete").order_by("place")
    steps = [
        ("draft", "Черновик", True),
        ("published", "Опубликован", comp.is_published),
        ("running", "Идёт", comp.is_published and comp.start_at <= timezone.now()),
        ("finished", "Завершён", comp.is_finished),
        ("results", "Итоги", comp.results_published),
    ]
    return render(request, "panel/competition.html", {
        "c": comp, "tab": tab, "tasks": tasks, "regs": regs, "subs": subs[:200], "sfilter": sfilter,
        "pending_count": pending_count, "standings": standings, "standings_tasks": standings_tasks,
        "results": results, "steps": steps, "nav": "competitions",
        "total_max": sum(t.max_score for t in tasks), "subs_total": comp.submissions.count(),
    })


def _back(comp, tab="overview"):
    return redirect(reverse("panel:competition", args=[comp.pk]) + f"?tab={tab}")


@require_POST
@organizer_required
def competition_action(request, pk, action):
    comp = get_object_or_404(Competition, pk=pk)
    now = timezone.now()
    if action == "publish":
        if comp.has_contest and not comp.tasks.exists():
            messages.error(request, "Добавьте хотя бы одно задание перед публикацией")
        else:
            comp.is_published, comp.published_at = True, now
            comp.save(update_fields=["is_published", "published_at"])
            messages.success(request, "Соревнование опубликовано — спортсмены видят его и могут зарегистрироваться")
    elif action == "unpublish":
        if comp.submissions.exists() or comp.results_published:
            messages.error(request, "Нельзя снять с публикации: уже есть решения или итоги")
        else:
            comp.is_published = False
            comp.save(update_fields=["is_published"])
            messages.info(request, "Соревнование возвращено в черновики")
    elif action == "start":
        if comp.is_finished:
            messages.error(request, "Соревнование уже завершено")
        else:
            dur = comp.duration
            comp.start_at = now
            if comp.end_at <= now:
                comp.end_at = now + dur
            if not comp.is_published:
                comp.is_published, comp.published_at = True, now
            comp.save()
            for r in comp.registrations.select_related("athlete"):
                Notification.send(r.athlete, f"«{comp.title}» началось! Задания доступны.", comp.get_absolute_url(), "start")
            messages.success(request, "Соревнование запущено — задания открыты участникам")
    elif action == "finish":
        if not comp.is_running:
            messages.error(request, "Завершить можно только идущее соревнование")
        else:
            comp.end_at = now
            comp.save(update_fields=["end_at"])
            messages.success(request, "Приём решений закрыт. Проверьте решения и подведите итоги.")
    elif action == "finalize":
        pending = comp.submissions.filter(status="pending").count()
        if not comp.is_finished:
            messages.error(request, "Итоги подводятся после завершения соревнования")
        elif pending:
            messages.error(request, f"Остались непроверенные решения: {pending}. Проверьте их перед подведением итогов.")
            return _back(comp, "submissions")
        elif not comp.has_contest and not comp.results.exists():
            messages.error(request, "Внесите результаты вручную перед публикацией")
            return redirect("panel:manual_results", pk=comp.pk)
        else:
            n = publish_results(comp)
            messages.success(request, f"Итоги опубликованы: {n} участников. Профили и рейтинг обновлены.")
        return _back(comp, "results")
    elif action == "unfinalize":
        unpublish_results(comp)
        messages.info(request, "Итоги отозваны, рейтинг пересчитан")
        return _back(comp, "results")
    elif action == "delete":
        if comp.submissions.exists() or comp.results.exists():
            messages.error(request, "Нельзя удалить соревнование с решениями или результатами")
        else:
            title = comp.title
            comp.delete()
            messages.success(request, f"«{title}» удалено")
            return redirect("panel:competitions")
    else:
        raise Http404
    return _back(comp)


# ================================================================== задания
@organizer_required
def task_edit(request, pk, tid=None):
    comp = get_object_or_404(Competition, pk=pk)
    task = get_object_or_404(Task, pk=tid, competition=comp) if tid else None
    form = forms.TaskForm(request.POST or None, request.FILES or None, instance=task,
                          initial={} if task else {"max_score": 100, "limits": "1 с · 256 МБ"})
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        if task is None:
            t.competition = comp
            n = comp.tasks.count()
            t.order = n + 1
            t.letter = f"_new{n}"
        t.save()
        Task.reletter(comp)
        messages.success(request, "Задание сохранено")
        if "add_more" in request.POST:
            return redirect("panel:task_add", pk=comp.pk)
        return _back(comp, "tasks")
    return render(request, "panel/task_form.html", {"form": form, "c": comp, "task": task, "nav": "competitions"})


@require_POST
@organizer_required
def task_action(request, pk, tid, action):
    comp = get_object_or_404(Competition, pk=pk)
    task = get_object_or_404(Task, pk=tid, competition=comp)
    if action == "delete":
        if task.submissions.exists():
            messages.error(request, "Нельзя удалить задание, по которому уже есть решения")
        else:
            task.delete()
            Task.reletter(comp)
            messages.success(request, "Задание удалено")
    elif action in ("up", "down"):
        tasks = list(comp.tasks.order_by("order", "id"))
        i = tasks.index(task)
        j = i - 1 if action == "up" else i + 1
        if 0 <= j < len(tasks):
            tasks[i], tasks[j] = tasks[j], tasks[i]
            with transaction.atomic():
                for k, t in enumerate(tasks):
                    Task.objects.filter(pk=t.pk).update(order=k + 1)
                Task.reletter(comp)
    elif action == "clear_file":
        task.attachment.delete(save=False)
        task.attachment_name = ""
        task.save()
    return _back(comp, "tasks")


# ================================================================== участники
@require_POST
@organizer_required
def participant_remove(request, pk, rid):
    comp = get_object_or_404(Competition, pk=pk)
    reg = get_object_or_404(Registration, pk=rid, competition=comp)
    if comp.submissions.filter(athlete=reg.athlete).exists():
        messages.error(request, "У участника есть решения — удалить заявку нельзя")
    else:
        reg.delete()
        messages.info(request, "Заявка удалена")
    return _back(comp, "participants")


@require_POST
@organizer_required
def participant_add(request, pk):
    comp = get_object_or_404(Competition, pk=pk)
    uid = request.POST.get("athlete", "")
    athlete = User.objects.filter(pk=uid, role=User.Role.ATHLETE, is_active=True).first() if uid.isdigit() else None
    if athlete:
        Registration.objects.get_or_create(competition=comp, athlete=athlete)
        messages.success(request, f"{athlete.full_name} добавлен(а) в участники")
    else:
        messages.error(request, "Спортсмен не найден")
    return redirect(request.POST.get("back") == "manual" and reverse("panel:manual_results", args=[comp.pk])
                    or reverse("panel:competition", args=[comp.pk]) + "?tab=participants")


# ================================================================== ручные результаты
@organizer_required
def manual_results(request, pk):
    comp = get_object_or_404(Competition, pk=pk)
    regs = list(comp.registrations.select_related("athlete__qualification").order_by("athlete__last_name"))
    existing = {r.athlete_id: r for r in comp.results.all()}
    if request.method == "POST":
        if comp.results_published:
            messages.error(request, "Сначала отзовите опубликованные итоги")
            return redirect("panel:manual_results", pk=pk)
        pairs, explicit = [], {}
        errors = []
        for reg in regs:
            raw = request.POST.get(f"score_{reg.athlete_id}", "").strip().replace(",", ".")
            place_raw = request.POST.get(f"place_{reg.athlete_id}", "").strip()
            if not raw and not place_raw:
                continue
            try:
                score = float(raw) if raw else 0.0
                if score < 0 or score > 100000:
                    raise ValueError
                place = int(place_raw) if place_raw else None
                if place is not None and not 1 <= place <= 10000:
                    raise ValueError
            except ValueError:
                errors.append(reg.athlete.full_name)
                continue
            pairs.append((reg.athlete, score))
            if place:
                explicit[reg.athlete_id] = place
        if errors:
            messages.error(request, "Некорректные значения у: " + ", ".join(errors))
            return redirect("panel:manual_results", pk=pk)
        with transaction.atomic():
            comp.results.all().delete()
            for athlete, score, place in assign_places(pairs):
                Result.objects.create(competition=comp, athlete=athlete, score=score,
                                      place=explicit.get(athlete.id, place), is_manual=True)
        messages.success(request, f"Сохранено результатов: {len(pairs)}. Опубликуйте итоги, чтобы обновить рейтинг.")
        return redirect("panel:manual_results", pk=pk)
    for r in regs:
        r.res = existing.get(r.athlete_id)
    athletes = User.objects.filter(role=User.Role.ATHLETE, is_active=True).exclude(
        registrations__competition=comp).order_by("last_name")
    return render(request, "panel/manual_results.html", {"c": comp, "regs": regs, "athletes": athletes,
                                                         "nav": "competitions"})


# ================================================================== проверка решений
@organizer_required
def submissions(request):
    qs = Submission.objects.select_related("athlete", "task", "competition")
    status = request.GET.get("status", "pending")
    if status in Submission.Status.values:
        qs = qs.filter(status=status)
    comp = request.GET.get("competition", "")
    if comp.isdigit():
        qs = qs.filter(competition_id=int(comp))
    qs = qs.order_by("created_at" if status == "pending" else "-created_at")
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    return render(request, "panel/submissions.html", {
        "page": page, "status": status, "comp": comp, "nav": "submissions",
        "competitions": Competition.objects.filter(has_contest=True).order_by("-start_at"),
        "pending_total": Submission.objects.filter(status="pending").count(),
    })


@organizer_required
def review(request, sid):
    sub = get_object_or_404(Submission.objects.select_related("athlete", "task", "competition", "reviewed_by"), pk=sid)
    form = forms.ReviewForm(request.POST or None, instance=sub)
    if request.method == "POST" and form.is_valid():
        if sub.competition.results_published:
            messages.error(request, "Итоги уже опубликованы — отзовите их, чтобы изменить оценку")
            return redirect("panel:review", sid=sid)
        s = form.save(commit=False)
        s.status = Submission.Status.REVIEWED
        s.reviewed_by = request.user
        s.reviewed_at = timezone.now()
        s.save()
        Notification.send(s.athlete, f"Решение #{s.pk} (задача {s.task.letter}, «{s.competition.title}») проверено: "
                                     f"{s.score} из {s.task.max_score}", reverse("competitions:submission", args=[s.pk]), "review")
        messages.success(request, f"Оценка сохранена: {s.score} / {s.task.max_score}")
        if "next" in request.POST:
            nxt = (Submission.objects.filter(status="pending", competition=sub.competition).order_by("created_at").first()
                   or Submission.objects.filter(status="pending").order_by("created_at").first())
            if nxt:
                return redirect("panel:review", sid=nxt.pk)
            messages.info(request, "Все решения проверены 🎉")
            return redirect(reverse("panel:competition", args=[sub.competition_id]) + "?tab=results")
        return redirect("panel:review", sid=sid)
    others = (Submission.objects.filter(task=sub.task, athlete=sub.athlete).exclude(pk=sub.pk).order_by("-created_at"))
    queue_left = Submission.objects.filter(status="pending").exclude(pk=sub.pk).count()
    return render(request, "panel/review.html", {"s": sub, "form": form, "others": others,
                                                 "queue_left": queue_left, "nav": "submissions",
                                                 "lines": range(1, sub.line_count + 1)})


# ================================================================== спортсмены
@organizer_required
def athletes(request):
    qs = User.objects.filter(role=User.Role.ATHLETE).select_related("qualification").annotate(
        nregs=Count("registrations", distinct=True))
    q = request.GET.get("q", "").strip()[:80]
    if q:
        qs = qs.filter(Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(email__icontains=q)
                       | Q(username__icontains=q) | Q(city__icontains=q))
    flt = request.GET.get("f", "")
    if flt == "unverified":
        qs = qs.filter(qualification__isnull=False, qualification_verified=False, qualification__points__gt=0)
    elif flt == "inactive":
        qs = qs.filter(is_active=False)
    qs = qs.order_by("-rating", "last_name")
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    return render(request, "panel/athletes.html", {"page": page, "q": q, "f": flt, "nav": "athletes"})


@organizer_required
def athlete_edit(request, uid):
    athlete = get_object_or_404(User, pk=uid, role=User.Role.ATHLETE)
    form = forms.AthleteAdminForm(request.POST or None, instance=athlete)
    if request.method == "POST" and form.is_valid():
        before = User.objects.get(pk=uid)
        form.save()
        if (before.qualification_verified, before.qualification_id) != (athlete.qualification_verified, athlete.qualification_id):
            rating.recalculate(reason="Изменение спортивной квалификации")
            if athlete.qualification_verified:
                Notification.send(athlete, f"Разряд «{athlete.qualification}» подтверждён организатором",
                                  reverse("accounts:profile"), "verify")
        messages.success(request, "Данные спортсмена обновлены")
        return redirect("panel:athlete", uid=uid)
    return render(request, "panel/athlete.html", {
        "a": athlete, "form": form, "nav": "athletes",
        "results": athlete.results.select_related("competition").order_by("-competition__end_at"),
        "regs": athlete.registrations.select_related("competition").order_by("-created_at"),
    })


@require_POST
@organizer_required
def rating_recalculate(request):
    n = rating.recalculate(reason="Плановый пересчёт (организатор)")
    messages.success(request, f"Рейтинг пересчитан. Изменений: {n}")
    return redirect(request.POST.get("back") == "dir" and reverse("panel:crud", args=["levels"]) or reverse("panel:dashboard"))


# ================================================================== справочники и контент (CRUD)
CRUD = {
    "disciplines": {"model": Discipline, "form": forms.DisciplineForm, "title": "Дисциплины", "group": "dir",
                    "cols": [("name", "Название"), ("code", "Код"), ("is_active", "Активна")], "one": "дисциплину"},
    "levels": {"model": CompetitionLevel, "form": forms.LevelForm, "title": "Уровни соревнований", "group": "dir",
               "cols": [("name", "Уровень"), ("coefficient", "Коэф. K_ур")], "one": "уровень",
               "hint": "Коэффициент уровня умножает рейтинговые очки за соревнование. После изменения пересчитайте рейтинг."},
    "qualifications": {"model": Qualification, "form": forms.QualificationForm, "title": "Разряды и звания", "group": "dir",
                       "cols": [("name", "Название"), ("short", "Кратко"), ("points", "Бонус Q")], "one": "разряд",
                       "hint": "Бонус Q добавляется к рейтингу спортсмена после подтверждения разряда организатором."},
    "news": {"model": News, "form": forms.NewsForm, "title": "Новости", "group": "content",
             "cols": [("title", "Заголовок"), ("tag", "Рубрика"), ("published_at", "Дата"), ("is_published", "Опубл.")], "one": "новость"},
    "documents": {"model": Document, "form": forms.DocumentForm, "title": "Документы и материалы", "group": "content",
                  "cols": [("title", "Название"), ("get_category_display", "Раздел"), ("is_published", "Опубл.")], "one": "документ"},
    "faq": {"model": FAQ, "form": forms.FAQForm, "title": "FAQ", "group": "content",
            "cols": [("question", "Вопрос"), ("category", "Категория"), ("is_published", "Опубл.")], "one": "вопрос"},
}


def _crud(key):
    cfg = CRUD.get(key)
    if not cfg:
        raise Http404
    return cfg


@organizer_required
def crud_list(request, key):
    cfg = _crud(key)
    items = cfg["model"].objects.all()
    rows = []
    for obj in items:
        vals = []
        for f, _ in cfg["cols"]:
            v = getattr(obj, f)
            vals.append(v() if callable(v) else v)
        rows.append((obj, vals))
    return render(request, "panel/crud_list.html", {"cfg": cfg, "key": key, "rows": rows, "nav": key,
                                                    "sections": CRUD})


@organizer_required
def crud_edit(request, key, pk=None):
    cfg = _crud(key)
    obj = get_object_or_404(cfg["model"], pk=pk) if pk else None
    form = cfg["form"](request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        o = form.save(commit=False)
        if key == "news" and not o.author_id:
            o.author = request.user
        o.save()
        messages.success(request, "Сохранено")
        return redirect("panel:crud", key=key)
    return render(request, "panel/crud_form.html", {"cfg": cfg, "key": key, "form": form, "obj": obj, "nav": key})


@require_POST
@organizer_required
def crud_delete(request, key, pk):
    cfg = _crud(key)
    obj = get_object_or_404(cfg["model"], pk=pk)
    try:
        obj.delete()
        messages.success(request, "Удалено")
    except ProtectedError:
        messages.error(request, "Нельзя удалить: запись используется в соревнованиях")
    return redirect("panel:crud", key=key)
