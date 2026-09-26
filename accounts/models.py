from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.urls import reverse


class User(AbstractUser):
    class Role(models.TextChoices):
        ATHLETE = "athlete", "Спортсмен"
        ORGANIZER = "organizer", "Организатор"

    role = models.CharField("Роль", max_length=16, choices=Role.choices, default=Role.ATHLETE, db_index=True)
    email = models.EmailField("Email", unique=True)
    middle_name = models.CharField("Отчество", max_length=150, blank=True)
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    city = models.CharField("Город", max_length=120, blank=True)
    institution = models.CharField("Учебное заведение / организация", max_length=200, blank=True)
    qualification = models.ForeignKey(
        "core.Qualification", verbose_name="Разряд / звание", null=True, blank=True, on_delete=models.SET_NULL
    )
    qualification_verified = models.BooleanField("Разряд подтверждён", default=False)
    disciplines = models.ManyToManyField("core.Discipline", verbose_name="Дисциплины", blank=True)
    bio = models.CharField("О себе", max_length=500, blank=True)

    # Приватность
    is_profile_public = models.BooleanField("Публичный профиль", default=True)
    show_institution = models.BooleanField("Показывать учебное заведение", default=True)
    consent_at = models.DateTimeField("Согласие на обработку ПД", null=True, blank=True)

    # Денормализованный рейтинг (пересчитывается сервисом rating.services)
    rating = models.FloatField("Рейтинг", default=0, db_index=True)
    rating_position = models.PositiveIntegerField("Место в рейтинге", null=True, blank=True)

    objects = UserManager()

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name or self.username

    @property
    def is_organizer(self):
        return self.role == self.Role.ORGANIZER or self.is_superuser

    @property
    def is_athlete(self):
        return self.role == self.Role.ATHLETE and not self.is_superuser

    @property
    def full_name(self):
        return " ".join(p for p in [self.last_name, self.first_name, self.middle_name] if p).strip()

    @property
    def short_name(self):
        if self.last_name and self.first_name:
            s = f"{self.last_name} {self.first_name[0]}."
            if self.middle_name:
                s += f" {self.middle_name[0]}."
            return s
        return self.username

    @property
    def display_name(self):
        n = " ".join(p for p in [self.first_name, self.last_name] if p)
        return n or self.username

    @property
    def initials(self):
        a = (self.first_name[:1] + self.last_name[:1]).upper()
        return a or self.username[:2].upper()

    @property
    def avatar_hue(self):
        return (self.pk or 0) * 47 % 360

    @property
    def effective_qualification(self):
        return self.qualification if self.qualification_verified else None

    def get_absolute_url(self):
        return reverse("accounts:athlete", args=[self.pk])
