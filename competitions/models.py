import string
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


def task_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()[:10]
    return f"tasks/{uuid.uuid4().hex}{ext}"


def submission_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()[:10]
    return f"submissions/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


class CompetitionQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_published=True)

    def running(self):
        now = timezone.now()
        return self.visible().filter(start_at__lte=now, end_at__gt=now)

    def upcoming(self):
        return self.visible().filter(start_at__gt=timezone.now())

    def finished(self):
        return self.visible().filter(end_at__lte=timezone.now())

    def with_status(self, status):
        now = timezone.now()
        if status == Competition.Status.DRAFT:
            return self.filter(is_published=False)
        if status == Competition.Status.PUBLISHED:
            return self.upcoming()
        if status == Competition.Status.RUNNING:
            return self.running()
        if status == Competition.Status.FINISHED:
            return self.finished()
        return self


class Competition(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        RUNNING = "running", "Идёт"
        FINISHED = "finished", "Завершён"

    class Format(models.TextChoices):
        ONLINE = "online", "Онлайн"
        OFFLINE = "offline", "Очно"
        HYBRID = "hybrid", "Смешанный"

    title = models.CharField("Название", max_length=200)
    short_description = models.CharField("Краткое описание", max_length=300)
    description = models.TextField("Подробное описание", blank=True)
    rules = models.TextField("Правила и инструкция для участников", blank=True)
    discipline = models.ForeignKey("core.Discipline", verbose_name="Дисциплина", on_delete=models.PROTECT)
    level = models.ForeignKey("core.CompetitionLevel", verbose_name="Уровень", on_delete=models.PROTECT)
    format = models.CharField("Формат", max_length=10, choices=Format.choices, default=Format.ONLINE)
    location = models.CharField("Место проведения", max_length=200, blank=True, default="Онлайн, платформа ФСП Контест")

    start_at = models.DateTimeField("Начало", db_index=True)
    end_at = models.DateTimeField("Окончание", db_index=True)
    registration_start = models.DateTimeField("Начало регистрации", null=True, blank=True)
    registration_end = models.DateTimeField("Окончание регистрации", null=True, blank=True,
                                            help_text="Если не указано — регистрация открыта до окончания соревнования")
    max_participants = models.PositiveIntegerField("Лимит участников", null=True, blank=True)

    has_contest = models.BooleanField(
        "Контест на платформе", default=True,
        help_text="Задания и отправка решений на платформе. Выключите для очных/внешних соревнований — результаты вносятся вручную.",
    )
    max_attempts = models.PositiveIntegerField("Попыток на задачу", default=10,
                                               validators=[MinValueValidator(1), MaxValueValidator(100)])
    show_live_standings = models.BooleanField("Показывать предварительную таблицу во время тура", default=True)

    external_platform = models.CharField("Внешняя платформа", max_length=80, blank=True, help_text="Например: Codeforces")
    external_url = models.URLField("Ссылка на внешнее соревнование", blank=True)

    is_published = models.BooleanField("Опубликован", default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    results_published = models.BooleanField("Итоги подведены", default=False, editable=False)
    results_published_at = models.DateTimeField(null=True, blank=True, editable=False)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="created_competitions", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompetitionQuerySet.as_manager()

    class Meta:
        ordering = ["-start_at"]
        verbose_name = "соревнование"
        verbose_name_plural = "соревнования"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("competitions:detail", args=[self.pk])

    # --- статус -----------------------------------------------------------
    @property
    def status(self):
        if not self.is_published:
            return self.Status.DRAFT
        now = timezone.now()
        if now < self.start_at:
            return self.Status.PUBLISHED
        if now < self.end_at:
            return self.Status.RUNNING
        return self.Status.FINISHED

    @property
    def status_label(self):
        return self.Status(self.status).label

    @property
    def is_running(self):
        return self.status == self.Status.RUNNING

    @property
    def is_finished(self):
        return self.status == self.Status.FINISHED

    @property
    def is_upcoming(self):
        return self.status == self.Status.PUBLISHED

    @property
    def duration(self):
        return self.end_at - self.start_at

    @property
    def duration_label(self):
        total = int(self.duration.total_seconds() // 60)
        d, rem = divmod(total, 1440)
        h, m = divmod(rem, 60)
        parts = []
        if d:
            parts.append(f"{d} д")
        if h:
            parts.append(f"{h} ч")
        if m:
            parts.append(f"{m} мин")
        return " ".join(parts) or "—"

    @property
    def progress_percent(self):
        if self.status != self.Status.RUNNING:
            return 100 if self.is_finished else 0
        total = self.duration.total_seconds() or 1
        return int(min(100, max(0, (timezone.now() - self.start_at).total_seconds() / total * 100)))

    # --- регистрация ------------------------------------------------------
    @property
    def registration_deadline(self):
        return self.registration_end or self.end_at

    @property
    def participants_count(self):
        if hasattr(self, "_participants_count"):
            return self._participants_count
        return self.registrations.count()

    def registration_state(self):
        """(открыта?, причина)"""
        now = timezone.now()
        if not self.is_published:
            return False, "Соревнование ещё не опубликовано"
        if self.registration_start and now < self.registration_start:
            return False, f"Регистрация откроется {timezone.localtime(self.registration_start):%d.%m.%Y %H:%M}"
        if now >= self.registration_deadline:
            return False, "Регистрация завершена"
        if self.max_participants and self.participants_count >= self.max_participants:
            return False, "Достигнут лимит участников"
        return True, ""

    @property
    def registration_open(self):
        return self.registration_state()[0]

    @property
    def total_max_score(self):
        return sum(t.max_score for t in self.tasks.all())


class Registration(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="registrations")
    athlete = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="registrations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("competition", "athlete")]
        ordering = ["created_at"]
        verbose_name = "заявка"
        verbose_name_plural = "заявки"

    def __str__(self):
        return f"{self.athlete} → {self.competition}"


class Task(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="tasks")
    order = models.PositiveIntegerField("Порядок", default=0)
    letter = models.CharField("Индекс", max_length=3, editable=False)
    title = models.CharField("Название", max_length=200)
    statement = models.TextField("Условие", help_text="Разметка: ## заголовок, - список, **жирный**, `код`, ``` блок кода ```")
    input_spec = models.TextField("Формат входных данных", blank=True)
    output_spec = models.TextField("Формат выходных данных", blank=True)
    sample_input = models.TextField("Пример ввода", blank=True)
    sample_output = models.TextField("Пример вывода", blank=True)
    notes = models.TextField("Примечание", blank=True)
    limits = models.CharField("Ограничения", max_length=80, blank=True, default="1 с · 256 МБ")
    max_score = models.PositiveIntegerField("Максимальный балл", default=100,
                                            validators=[MinValueValidator(1), MaxValueValidator(10000)])
    attachment = models.FileField("Файл-материал", upload_to=task_upload_to, blank=True)
    attachment_name = models.CharField(max_length=200, blank=True, editable=False)
    link = models.URLField("Ссылка на материалы", blank=True)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("competition", "letter")]
        verbose_name = "задание"
        verbose_name_plural = "задания"

    def __str__(self):
        return f"{self.letter}. {self.title}"

    def get_absolute_url(self):
        return reverse("competitions:task", args=[self.competition_id, self.letter])

    @staticmethod
    def letter_for(index):
        letters = string.ascii_uppercase
        return letters[index] if index < 26 else f"Z{index - 25}"

    @classmethod
    def reletter(cls, competition):
        tasks = list(competition.tasks.order_by("order", "id"))
        # двухфазное переименование, чтобы не нарушить unique_together
        for i, t in enumerate(tasks):
            cls.objects.filter(pk=t.pk).update(letter=f"_{i}")
        for i, t in enumerate(tasks):
            cls.objects.filter(pk=t.pk).update(letter=cls.letter_for(i), order=i + 1)


class Submission(models.Model):
    class Language(models.TextChoices):
        PY = "python", "Python 3"
        CPP = "cpp", "C++ 17"
        C = "c", "C"
        JAVA = "java", "Java"
        CS = "csharp", "C#"
        KT = "kotlin", "Kotlin"
        GO = "go", "Go"
        JS = "js", "JavaScript"
        PAS = "pascal", "Pascal"
        OTHER = "other", "Другой / текстовый ответ"

    class Status(models.TextChoices):
        PENDING = "pending", "На проверке"
        REVIEWED = "reviewed", "Проверено"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="submissions")
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="submissions")
    athlete = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    language = models.CharField("Язык", max_length=16, choices=Language.choices, default=Language.PY)
    code = models.TextField("Код решения", blank=True)
    file = models.FileField("Файл решения", upload_to=submission_upload_to, blank=True)
    original_filename = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    score = models.PositiveIntegerField("Баллы", null=True, blank=True)
    comment = models.TextField("Комментарий проверяющего", blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="reviewed_submissions")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "решение"
        verbose_name_plural = "решения"

    def __str__(self):
        return f"#{self.pk} {self.athlete} · {self.task}"

    @property
    def attempt_number(self):
        return Submission.objects.filter(task=self.task, athlete=self.athlete, created_at__lte=self.created_at).count()

    @property
    def elapsed_minutes(self):
        return max(0, int((self.created_at - self.competition.start_at).total_seconds() // 60))

    @property
    def verdict(self):
        if self.status == self.Status.PENDING:
            return "pending", "На проверке"
        if self.score == self.task.max_score:
            return "full", "Полное решение"
        if self.score:
            return "partial", "Частичное"
        return "zero", "Не зачтено"

    @property
    def line_count(self):
        return self.code.count("\n") + 1 if self.code else 0


class Result(models.Model):
    """Итоговый результат спортсмена в соревновании (связка Соревнование → Профиль → Рейтинг)."""
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="results")
    athlete = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="results")
    place = models.PositiveIntegerField("Место")
    score = models.FloatField("Баллы", default=0)
    penalty = models.PositiveIntegerField("Штрафное время, мин", default=0)
    solved = models.PositiveIntegerField("Решено задач", default=0)
    details = models.JSONField(default=dict, blank=True)
    participants_total = models.PositiveIntegerField(default=0)
    rating_points = models.FloatField("Рейтинговые очки", default=0)
    is_manual = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["competition", "place"]
        unique_together = [("competition", "athlete")]
        verbose_name = "результат"
        verbose_name_plural = "результаты"

    def __str__(self):
        return f"{self.competition}: {self.athlete} — {self.place}"

    @property
    def medal(self):
        return {1: "gold", 2: "silver", 3: "bronze"}.get(self.place, "")

    @property
    def diploma(self):
        if self.place == 1:
            return "Победитель"
        if self.place in (2, 3):
            return "Призёр"
        return ""
