import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


def material_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()[:10]
    return f"materials/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


# ---------------------------------------------------------------- Справочники
class Discipline(models.Model):
    """Дисциплина спортивного программирования."""
    name = models.CharField("Название", max_length=120, unique=True)
    code = models.CharField("Короткий код", max_length=16, blank=True, help_text="Например: ALG, PROD, CTF")
    description = models.TextField("Описание", blank=True)
    is_active = models.BooleanField("Активна", default=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "дисциплина"
        verbose_name_plural = "дисциплины"

    def __str__(self):
        return self.name


class CompetitionLevel(models.Model):
    """Уровень соревнования. Коэффициент используется в рейтинговой модели."""
    name = models.CharField("Название", max_length=120, unique=True)
    coefficient = models.DecimalField("Коэффициент рейтинга", max_digits=4, decimal_places=2, default=1)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "-coefficient"]
        verbose_name = "уровень соревнования"
        verbose_name_plural = "уровни соревнований"

    def __str__(self):
        return self.name


class Qualification(models.Model):
    """Спортивный разряд / звание. Баллы — стартовый бонус в рейтинге."""
    name = models.CharField("Название", max_length=120, unique=True)
    short = models.CharField("Сокращение", max_length=16)
    points = models.PositiveIntegerField("Бонус к рейтингу", default=0)
    order = models.PositiveIntegerField("Порядок (от высшего)", default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "разряд / звание"
        verbose_name_plural = "разряды и звания"

    def __str__(self):
        return self.name


# ---------------------------------------------------------------- Контент
class News(models.Model):
    title = models.CharField("Заголовок", max_length=200)
    excerpt = models.CharField("Анонс", max_length=300, blank=True)
    body = models.TextField("Текст")
    tag = models.CharField("Рубрика", max_length=40, blank=True, default="Новости")
    is_pinned = models.BooleanField("Закрепить", default=False)
    is_published = models.BooleanField("Опубликована", default=True)
    published_at = models.DateTimeField("Дата публикации", default=timezone.now)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False)

    class Meta:
        ordering = ["-is_pinned", "-published_at"]
        verbose_name = "новость"
        verbose_name_plural = "новости"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("core:news_detail", args=[self.pk])


class Document(models.Model):
    class Category(models.TextChoices):
        REGULATION = "regulation", "Положения"
        RULES = "rules", "Правила"
        OFFICIAL = "official", "Официальные документы"
        MATERIAL = "material", "Полезные материалы"

    title = models.CharField("Название", max_length=200)
    category = models.CharField("Раздел", max_length=20, choices=Category.choices, default=Category.REGULATION)
    description = models.CharField("Краткое описание", max_length=300, blank=True)
    body = models.TextField("Текст документа", blank=True, help_text="Поддерживается простая разметка: ## заголовок, - список, **жирный**, `код`.")
    file = models.FileField("Файл", upload_to=material_upload_to, blank=True)
    url = models.URLField("Внешняя ссылка", blank=True)
    is_published = models.BooleanField("Опубликован", default=True)
    published_at = models.DateTimeField("Дата", default=timezone.now)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["category", "order", "-published_at"]
        verbose_name = "документ"
        verbose_name_plural = "документы и материалы"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("core:document_detail", args=[self.pk])

    @property
    def file_ext(self):
        return Path(self.file.name).suffix.lstrip(".").upper() if self.file else ""


class FAQ(models.Model):
    question = models.CharField("Вопрос", max_length=300)
    answer = models.TextField("Ответ")
    category = models.CharField("Категория", max_length=60, default="Общее")
    order = models.PositiveIntegerField("Порядок", default=0)
    is_published = models.BooleanField("Опубликован", default=True)

    class Meta:
        ordering = ["category", "order", "id"]
        verbose_name = "вопрос FAQ"
        verbose_name_plural = "FAQ"

    def __str__(self):
        return self.question


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    text = models.CharField(max_length=300)
    url = models.CharField(max_length=300, blank=True)
    kind = models.CharField(max_length=20, default="info")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text

    @classmethod
    def send(cls, user, text, url="", kind="info"):
        return cls.objects.create(user=user, text=text[:300], url=url[:300], kind=kind)
