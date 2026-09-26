"""
Сквозные тесты основного сценария кейса:
организатор создаёт контест → добавляет задания → публикует → спортсмен
регистрируется → отправляет решение → организатор проверяет → итоги →
результат в профиле → рейтинг. Плюс проверки безопасности.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import CompetitionLevel, Discipline

from .models import Competition, Registration, Result, Submission, Task

User = get_user_model()


@override_settings(SUBMISSION_COOLDOWN_SECONDS=0)
class FullScenarioTest(TestCase):
    def setUp(self):
        self.org = User.objects.get(role=User.Role.ORGANIZER)
        self.org.set_password("Organizer#2026"); self.org.save()
        self.a1 = User.objects.create_user("a1", "a1@x.ru", "Pass#12345", first_name="Али", last_name="Алиев", role="athlete")
        self.a2 = User.objects.create_user("a2", "a2@x.ru", "Pass#12345", first_name="Бор", last_name="Борисов", role="athlete")

    def test_full_flow(self):
        c = self.client
        c.force_login(self.org)
        now = timezone.localtime()
        fmt = "%Y-%m-%dT%H:%M"
        r = c.post(reverse("panel:competition_new"), {
            "title": "Тест", "short_description": "Кратко", "discipline": Discipline.objects.first().pk,
            "level": CompetitionLevel.objects.first().pk, "format": "online", "location": "Онлайн",
            "start_at": (now + timedelta(hours=1)).strftime(fmt), "end_at": (now + timedelta(hours=3)).strftime(fmt),
            "has_contest": "on", "max_attempts": 5, "show_live_standings": "on", "description": "", "rules": "",
        })
        self.assertEqual(r.status_code, 302)
        comp = Competition.objects.get(title="Тест")
        self.assertEqual(comp.status, "draft")
        for i in range(3):
            r = c.post(reverse("panel:task_add", args=[comp.pk]), {"title": f"Задача {i}", "statement": "Условие", "max_score": 100, "limits": ""})
            self.assertEqual(r.status_code, 302)
        self.assertEqual(list(comp.tasks.values_list("letter", flat=True)), ["A", "B", "C"])
        c.post(reverse("panel:competition_action", args=[comp.pk, "publish"]))
        comp.refresh_from_db()
        self.assertEqual(comp.status, "published")

        # спортсмены регистрируются; до старта задания закрыты
        for a in (self.a1, self.a2):
            c.force_login(a)
            c.post(reverse("competitions:register", args=[comp.pk]))
            r = c.get(reverse("competitions:task", args=[comp.pk, "A"]))
            self.assertEqual(r.status_code, 302)
        self.assertEqual(Registration.objects.filter(competition=comp).count(), 2)

        c.force_login(self.org)
        c.post(reverse("panel:competition_action", args=[comp.pk, "start"]))
        comp.refresh_from_db()
        self.assertEqual(comp.status, "running")

        # отправка кодом и файлом
        c.force_login(self.a1)
        self.assertEqual(c.get(reverse("competitions:task", args=[comp.pk, "A"])).status_code, 200)
        c.post(reverse("competitions:submit", args=[comp.pk, "A"]), {"language": "python", "code": "print(1)"})
        f = SimpleUploadedFile("sol.cpp", b"int main(){}", content_type="text/plain")
        c.post(reverse("competitions:submit", args=[comp.pk, "B"]), {"language": "cpp", "code": "", "file": f})
        c.force_login(self.a2)
        c.post(reverse("competitions:submit", args=[comp.pk, "A"]), {"language": "python", "code": "print(2)"})
        self.assertEqual(Submission.objects.filter(competition=comp).count(), 3)
        sub_file = Submission.objects.get(athlete=self.a1, task__letter="B")
        self.assertIn("int main", sub_file.code)

        # чужое решение недоступно
        other = Submission.objects.filter(athlete=self.a1).first()
        self.assertEqual(c.get(reverse("competitions:submission", args=[other.pk])).status_code, 404)
        self.assertEqual(c.get(reverse("competitions:submission_download", args=[other.pk])).status_code, 404)
        # спортсмен не может в панель
        self.assertEqual(c.get(reverse("panel:dashboard")).status_code, 403)

        # проверка
        c.force_login(self.org)
        c.post(reverse("panel:competition_action", args=[comp.pk, "finish"]))
        # итоги не подводятся, пока есть непроверенные
        c.post(reverse("panel:competition_action", args=[comp.pk, "finalize"]))
        comp.refresh_from_db()
        self.assertFalse(comp.results_published)
        scores = {(self.a1.pk, "A"): 100, (self.a1.pk, "B"): 50, (self.a2.pk, "A"): 100}
        for s in Submission.objects.filter(competition=comp):
            r = c.post(reverse("panel:review", args=[s.pk]), {"score": scores[(s.athlete_id, s.task.letter)], "comment": "ok"})
            self.assertEqual(r.status_code, 302)
        # балл выше максимума отклоняется
        s = Submission.objects.first()
        c.post(reverse("panel:review", args=[s.pk]), {"score": 999})
        s.refresh_from_db()
        self.assertLessEqual(s.score, 100)

        c.post(reverse("panel:competition_action", args=[comp.pk, "finalize"]))
        comp.refresh_from_db()
        self.assertTrue(comp.results_published)
        r1 = Result.objects.get(competition=comp, athlete=self.a1)
        r2 = Result.objects.get(competition=comp, athlete=self.a2)
        self.assertEqual((r1.place, r1.score), (1, 150))
        self.assertEqual(r2.place, 2)
        self.a1.refresh_from_db()
        self.assertGreater(self.a1.rating, 0)
        self.assertEqual(self.a1.rating_position, 1)

        # результат в профиле
        c.force_login(self.a1)
        r = c.get(reverse("accounts:profile"))
        self.assertContains(r, "Тест")
        self.assertEqual(c.get(reverse("competitions:results_csv", args=[comp.pk])).status_code, 200)


class SecurityTest(TestCase):
    def test_login_throttle(self):
        User.objects.create_user("victim", "v@x.ru", "Correct#123", role="athlete")
        for _ in range(6):
            self.client.post(reverse("accounts:login"), {"username": "victim", "password": "wrong"})
        r = self.client.post(reverse("accounts:login"), {"username": "victim", "password": "Correct#123"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertIn("script-src 'self'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_markup_escapes_html(self):
        from core.templatetags.fsp import markup
        out = markup("<script>alert(1)</script> **b** [x](javascript:alert(1))")
        self.assertNotIn("<script>", out)
        self.assertNotIn('href="javascript', out)
        self.assertIn("<strong>b</strong>", out)

    def test_registration_requires_consent_and_hides_email(self):
        data = {"last_name": "Тестов", "first_name": "Тест", "username": "tt", "email": "tt@x.ru", "city": "Махачкала",
                "password1": "Strong#Pass1", "password2": "Strong#Pass1"}
        r = self.client.post(reverse("accounts:register"), data)
        self.assertFalse(User.objects.filter(username="tt").exists())
        data["consent"] = "on"
        self.client.post(reverse("accounts:register"), data)
        u = User.objects.get(username="tt")
        self.assertEqual(u.role, "athlete")
        self.client.logout()
        r = self.client.get(reverse("accounts:athlete", args=[u.pk]))
        self.assertNotContains(r, "tt@x.ru")

    def test_draft_hidden(self):
        org = User.objects.get(role=User.Role.ORGANIZER)
        c = Competition.objects.create(title="Секрет", short_description="x", discipline=Discipline.objects.first(),
                                       level=CompetitionLevel.objects.first(), start_at=timezone.now(),
                                       end_at=timezone.now() + timedelta(hours=1), created_by=org)
        self.assertEqual(self.client.get(c.get_absolute_url()).status_code, 404)


class DemoPagesTest(TestCase):
    """Все ключевые страницы открываются на демо-данных для обеих ролей."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_pages(self):
        comp = Competition.objects.get(title__startswith="Тестовый контест")
        running = Competition.objects.running().first()
        public = ["/", "/competitions/", f"/competitions/{comp.pk}/", f"/competitions/{comp.pk}/tasks/A/",
                  "/rating/", "/rating/?discipline=1", "/info/", "/info/news/", "/info/calendar/", "/info/documents/",
                  "/info/faq/", "/privacy/", f"/competitions/{comp.pk}/protocol/", "/accounts/login/", "/accounts/register/"]
        for url in public:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        athlete = User.objects.get(username="ivanov")
        self.client.force_login(athlete)
        for url in ["/accounts/profile/", "/accounts/profile/?tab=competitions", "/accounts/profile/?tab=contests",
                    "/accounts/settings/", "/notifications/", f"/competitions/{running.pk}/",
                    f"/competitions/{running.pk}/tasks/B/", "/accounts/export/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        org = User.objects.get(role=User.Role.ORGANIZER)
        self.client.force_login(org)
        sub = Submission.objects.filter(status="pending").first()
        urls = ["/panel/", "/panel/competitions/", "/panel/competitions/new/", "/panel/submissions/",
                f"/panel/submissions/{sub.pk}/", "/panel/athletes/", f"/panel/athletes/{athlete.pk}/"]
        for tab in ["overview", "tasks", "participants", "submissions", "results"]:
            urls.append(f"/panel/competitions/{running.pk}/?tab={tab}")
            urls.append(f"/panel/competitions/{comp.pk}/?tab={tab}")
        manual = Competition.objects.filter(has_contest=False).first()
        urls += [f"/panel/competitions/{manual.pk}/manual-results/", f"/panel/competitions/{comp.pk}/edit/",
                 f"/panel/competitions/{comp.pk}/tasks/{comp.tasks.first().pk}/"]
        for key in ["disciplines", "levels", "qualifications", "news", "documents", "faq"]:
            urls += [f"/panel/{key}/", f"/panel/{key}/new/"]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
