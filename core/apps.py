from django.apps import AppConfig
from django.db.models.signals import post_migrate


def ensure_default_data(sender, **kwargs):
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from .models import CompetitionLevel, Discipline, Qualification

    User = get_user_model()
    if not User.objects.filter(role=User.Role.ORGANIZER).exists():
        u = User(username=settings.DEFAULT_ORGANIZER_USERNAME, email=settings.DEFAULT_ORGANIZER_EMAIL,
                 first_name="Организатор", last_name="ФСП", role=User.Role.ORGANIZER, is_staff=True)
        u.set_password(settings.DEFAULT_ORGANIZER_PASSWORD)
        u.save()
    if not CompetitionLevel.objects.exists():
        for i, (n, k) in enumerate([("Чемпионат России", 2.0), ("Всероссийские соревнования", 1.6),
                                    ("Межрегиональные соревнования", 1.3), ("Региональные соревнования", 1.0),
                                    ("Муниципальные / отборочные", 0.7)]):
            CompetitionLevel.objects.create(name=n, coefficient=k, order=i)
    if not Qualification.objects.exists():
        for i, (n, s, p) in enumerate([
            ("Мастер спорта России международного класса", "МСМК", 300), ("Мастер спорта России", "МС", 220),
            ("Кандидат в мастера спорта", "КМС", 150), ("I спортивный разряд", "I", 100),
            ("II спортивный разряд", "II", 70), ("III спортивный разряд", "III", 45),
            ("I юношеский разряд", "I юн.", 25), ("II юношеский разряд", "II юн.", 15),
            ("III юношеский разряд", "III юн.", 8), ("Без разряда", "б/р", 0)]):
            Qualification.objects.create(name=n, short=s, points=p, order=i)
    if not Discipline.objects.exists():
        for i, (n, c, d) in enumerate([
            ("Алгоритмическое программирование", "ALG", "Олимпиадные задачи на алгоритмы и структуры данных."),
            ("Продуктовое программирование", "PROD", "Хакатоны: разработка работающего продукта под кейс."),
            ("Программирование систем информационной безопасности", "SEC", "Соревнования формата CTF."),
            ("Программирование робототехники", "ROBO", "Программирование роботов и автономных систем."),
            ("Программирование беспилотных авиационных систем", "UAV", "Автономные полёты и управление БАС.")]):
            Discipline.objects.create(name=n, code=c, description=d, order=i)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Платформа"

    def ready(self):
        post_migrate.connect(ensure_default_data, sender=self)
