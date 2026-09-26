from dataclasses import dataclass, field

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.models import Notification
from rating import services as rating

from .models import Competition, Result, Submission
# бизнес логика

@dataclass
class Cell:
    best: int = 0
    attempts: int = 0
    pending: int = 0
    time: int = 0
    reviewed: bool = False

    @property
    def state(self):
        if self.attempts == 0:
            return "none"
        if self.best and self.reviewed:
            return "scored"
        if self.pending:
            return "pending"
        return "zero"


@dataclass
class Row:
    athlete: object
    cells: dict = field(default_factory=dict)
    total: int = 0
    penalty: int = 0
    solved: int = 0
    place: int = 0
    attempts: int = 0
    pending: int = 0


def compute_standings(competition: Competition):
    tasks = list(competition.tasks.all())
    subs = (Submission.objects.filter(competition=competition)
            .select_related("athlete", "task").order_by("created_at"))
    rows = {}
    for s in subs:
        row = rows.get(s.athlete_id)
        if row is None:
            row = rows[s.athlete_id] = Row(athlete=s.athlete, cells={t.id: Cell() for t in tasks})
        cell = row.cells.setdefault(s.task_id, Cell())
        cell.attempts += 1
        row.attempts += 1
        if s.status == Submission.Status.PENDING:
            cell.pending += 1
            row.pending += 1
            continue
        cell.reviewed = True
        if (s.score or 0) > cell.best:
            cell.best = s.score or 0
            cell.time = max(0, int((s.created_at - competition.start_at).total_seconds() // 60))
    task_max = {t.id: t.max_score for t in tasks}
    for row in rows.values():
        row.total = sum(c.best for c in row.cells.values())
        row.penalty = sum(c.time for c in row.cells.values() if c.best > 0)
        row.solved = sum(1 for tid, c in row.cells.items() if c.best and c.best >= task_max.get(tid, 0))
    ordered = sorted(rows.values(), key=lambda r: (-r.total, r.penalty, r.athlete.last_name, r.athlete.id))
    prev = None
    for i, row in enumerate(ordered, start=1):
        key = (row.total, row.penalty)
        row.place = prev[1] if prev and prev[0] == key else i
        prev = (key, row.place)
    return tasks, ordered


def assign_places(pairs):
    ordered = sorted(pairs, key=lambda p: -p[1])
    out, prev_score, prev_place = [], None, 0
    for i, (a, s) in enumerate(ordered, start=1):
        place = prev_place if s == prev_score else i
        out.append((a, s, place))
        prev_score, prev_place = s, place
    return out


@transaction.atomic
def publish_results(competition: Competition, reason_user=None):
    if competition.has_contest:
        tasks, rows = compute_standings(competition)
        Result.objects.filter(competition=competition).delete()
        results = []
        for row in rows:
            results.append(Result(
                competition=competition, athlete=row.athlete, place=row.place, score=row.total,
                penalty=row.penalty, solved=row.solved,
                details={t.letter: row.cells[t.id].best for t in tasks},
            ))
        Result.objects.bulk_create(results)
    results = list(Result.objects.filter(competition=competition).select_related("athlete__qualification"))
    n = len(results)
    k_field = rating.field_coefficient([r.athlete for r in results])
    for r in results:
        r.participants_total = n
        earned = r.score > 0 or r.is_manual
        r.rating_points = rating.result_points(r.place, n, competition.level.coefficient, k_field) if earned else 0
    Result.objects.bulk_update(results, ["participants_total", "rating_points"])

    competition.results_published = True
    competition.results_published_at = timezone.now()
    competition.save(update_fields=["results_published", "results_published_at"])
    rating.recalculate(reason=f"Итоги: {competition.title}", competition=competition)

    url = reverse("competitions:detail", args=[competition.pk]) + "#results"
    for r in results:
        Notification.send(r.athlete, f"Итоги «{competition.title}»: {r.place} место, {r.score:g} баллов, "
                                     f"+{r.rating_points:g} к рейтингу", url, kind="result")
    return n


@transaction.atomic
def unpublish_results(competition: Competition):
    if competition.has_contest:
        Result.objects.filter(competition=competition).delete()
    competition.results_published = False
    competition.results_published_at = None
    competition.save(update_fields=["results_published", "results_published_at"])
    rating.recalculate(reason=f"Итоги отозваны: {competition.title}", competition=competition)
