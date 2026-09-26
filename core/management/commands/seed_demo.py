"""
Демонстрационные данные для защиты:
  python manage.py seed_demo          — заполнить (если база пустая)
  python manage.py seed_demo --reset  — пересоздать демо-данные
"""
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from competitions.models import Competition, Registration, Result, Submission, Task
from competitions.services import assign_places, publish_results
from core.apps import ensure_default_data
from core.models import FAQ, CompetitionLevel, Discipline, Document, News, Notification, Qualification
from rating.models import RatingHistory

ATHLETE_PASSWORD = "Athlete#2026"

ATHLETES = [
    # username, last, first, middle, city, institution, qualification short, verified
    ("ivanov", "Иванов", "Алексей", "Сергеевич", "Махачкала", "ДГТУ, факультет компьютерных технологий", "I", True),
    ("magomedov", "Магомедов", "Шамиль", "Ахмедович", "Махачкала", "Республиканский физико-математический лицей", "КМС", True),
    ("alieva", "Алиева", "Патимат", "Руслановна", "Каспийск", "ДГУ, факультет математики и КН", "КМС", True),
    ("gasanov", "Гасанов", "Руслан", "Магомедович", "Дербент", "Лицей №2 г. Дербент", "II", True),
    ("abdullaeva", "Абдуллаева", "Амина", "Исаевна", "Махачкала", "ДГТУ, ИВТ", "I", True),
    ("kurbanov", "Курбанов", "Тимур", "Альбертович", "Хасавюрт", "Гимназия №3", "III", True),
    ("omarov", "Омаров", "Ислам", "Гаджиевич", "Буйнакск", "ДГУ, ИКБ", "II", False),
    ("petrova", "Петрова", "Мария", "Андреевна", "Кизляр", "Кизлярский колледж", "I юн.", True),
    ("rasulov", "Расулов", "Арсен", "Маратович", "Махачкала", "Лицей №39", "КМС", False),
    ("ismailova", "Исмаилова", "Салима", "Камиловна", "Избербаш", "ДГПУ", "III", True),
    ("nuriev", "Нуриев", "Эльдар", "Фикретович", "Дербент", "ДГТУ, филиал в Дербенте", "II", True),
    ("yusupov", "Юсупов", "Magomed".replace("Magomed", "Магомед"), "Шамилевич", "Каспийск", "Лицей №1 г. Каспийск", "I", True),
    ("sidorov", "Сидоров", "Никита", "Олегович", "Махачкала", "ДГУНХ", "б/р", False),
    ("khalilova", "Халилова", "Заира", "Тагировна", "Махачкала", "ДГТУ, факультет компьютерных технологий", "II юн.", True),
]

CODE_PY = '''import sys

def main():
    data = sys.stdin.read().split()
    n, q = int(data[0]), int(data[1])
    a = list(map(int, data[2:2 + n]))
    pref = [0] * (n + 1)
    for i, x in enumerate(a):
        pref[i + 1] = pref[i] + x
    out = []
    idx = 2 + n
    for _ in range(q):
        l, r = int(data[idx]), int(data[idx + 1])
        idx += 2
        out.append(pref[r] - pref[l - 1])
    print("\\n".join(map(str, out)))

main()
'''

CODE_CPP = '''#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    long long best = a[0], cur = a[0];
    for (int i = 1; i < n; ++i) {
        cur = max(a[i], cur + a[i]);
        best = max(best, cur);
    }
    cout << best << "\\n";
    return 0;
}
'''

CODE_BFS = '''from collections import deque

n, m = map(int, input().split())
g = [input() for _ in range(n)]
sr = sc = tr = tc = 0
for i in range(n):
    for j in range(m):
        if g[i][j] == 'S': sr, sc = i, j
        if g[i][j] == 'T': tr, tc = i, j
dist = [[-1] * m for _ in range(n)]
dist[sr][sc] = 0
q = deque([(sr, sc)])
while q:
    r, c = q.popleft()
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < n and 0 <= nc < m and g[nr][nc] != '#' and dist[nr][nc] == -1:
            dist[nr][nc] = dist[r][c] + 1
            q.append((nr, nc))
print(dist[tr][tc])
'''

CODE_JAVA = '''import java.util.*;

public class Main {
    public static void main(String[] args) {
        Scanner in = new Scanner(System.in);
        String s = in.next();
        int bal = 0;
        for (char c : s.toCharArray()) {
            bal += c == '(' ? 1 : -1;
            if (bal < 0) { System.out.println("NO"); return; }
        }
        System.out.println(bal == 0 ? "YES" : "NO");
    }
}
'''

CODE_WRONG = '''n = int(input())
a = list(map(int, input().split()))
print(sum(a))  # TODO: учесть отрицательные
'''

CODES = [("python", CODE_PY), ("cpp", CODE_CPP), ("python", CODE_BFS), ("java", CODE_JAVA), ("python", CODE_WRONG)]


class Command(BaseCommand):
    help = "Заполняет базу демонстрационными данными (соревнования, участники, решения, результаты)"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Удалить существующие демо-данные и создать заново")

    def handle(self, *args, **opts):
        User = get_user_model()
        if Competition.objects.exists() and not opts["reset"]:
            self.stdout.write(self.style.WARNING("Данные уже есть. Используйте --reset для пересоздания."))
            return
        with transaction.atomic():
            if opts["reset"]:
                Submission.objects.all().delete()
                Result.objects.all().delete()
                Registration.objects.all().delete()
                Competition.objects.all().delete()
                RatingHistory.objects.all().delete()
                Notification.objects.all().delete()
                News.objects.all().delete()
                Document.objects.all().delete()
                FAQ.objects.all().delete()
                User.objects.filter(role=User.Role.ATHLETE).delete()
            ensure_default_data(None)
            self.rnd = random.Random(2026)
            self.now = timezone.now().replace(second=0, microsecond=0)
            self.org = User.objects.filter(role=User.Role.ORGANIZER).first()
            self.q = {q.short: q for q in Qualification.objects.all()}
            self.lv = {l.order: l for l in CompetitionLevel.objects.all()}
            self.disc = {d.code: d for d in Discipline.objects.all()}
            self.athletes = self._athletes()
            self._competitions()
            self._content()
        self.stdout.write(self.style.SUCCESS("Демо-данные созданы."))
        self.stdout.write(f"  Организатор: {settings.DEFAULT_ORGANIZER_USERNAME} / {settings.DEFAULT_ORGANIZER_PASSWORD}")
        self.stdout.write(f"  Спортсмен:   ivanov / {ATHLETE_PASSWORD}  (и другие: magomedov, alieva, gasanov …)")

    # ------------------------------------------------------------------
    def _athletes(self):
        User = get_user_model()
        out = []
        for i, (u, last, first, middle, city, inst, q, ver) in enumerate(ATHLETES):
            a = User(username=u, email=f"{u}@example.com", last_name=last, first_name=first, middle_name=middle,
                     city=city, institution=inst, qualification=self.q.get(q), qualification_verified=ver,
                     role=User.Role.ATHLETE, consent_at=self.now - timedelta(days=400 - i * 7),
                     birth_date=(self.now - timedelta(days=365 * (16 + i % 7) + i * 11)).date(),
                     bio="Люблю графы и динамическое программирование." if i % 3 == 0 else "")
            a.set_password(ATHLETE_PASSWORD)
            a.save()
            User.objects.filter(pk=a.pk).update(date_joined=self.now - timedelta(days=420 - i * 9))
            a.disciplines.set([self.disc["ALG"]] + ([self.disc["PROD"]] if i % 2 else []) + ([self.disc["SEC"]] if i % 5 == 0 else []))
            out.append(a)
        return out

    def _comp(self, **kw):
        defaults = dict(created_by=self.org, is_published=True, published_at=self.now - timedelta(days=30),
                        location="Онлайн, платформа ФСП Контест", format=Competition.Format.ONLINE)
        defaults.update(kw)
        return Competition.objects.create(**defaults)

    def _task(self, comp, i, title, statement, max_score=100, **kw):
        return Task.objects.create(competition=comp, order=i + 1, letter=Task.letter_for(i), title=title,
                                   statement=statement, max_score=max_score, **kw)

    def _sub(self, comp, task, athlete, minute, score=None, lang_code=None, comment=""):
        lang, code = lang_code or self.rnd.choice(CODES)
        s = Submission.objects.create(task=task, competition=comp, athlete=athlete, language=lang, code=code)
        fields = {"created_at": comp.start_at + timedelta(minutes=minute)}
        if score is not None:
            fields.update(status=Submission.Status.REVIEWED, score=score, reviewed_by=self.org,
                          reviewed_at=comp.start_at + timedelta(minutes=minute + 7), comment=comment)
        Submission.objects.filter(pk=s.pk).update(**fields)
        return s

    def _publish(self, comp):
        publish_results(comp)
        RatingHistory.objects.filter(competition=comp).update(created_at=comp.end_at + timedelta(hours=2))
        Competition.objects.filter(pk=comp.pk).update(results_published_at=comp.end_at + timedelta(hours=2))

    # ------------------------------------------------------------------
    def _competitions(self):
        A = self.athletes
        now = self.now

        # 1) Чемпионат (давний, очный) — показывает эффект давности
        c = self._comp(title="Отборочный этап Чемпионата России по спортивному программированию",
                       short_description="Региональный отбор на Чемпионат России, алгоритмическая дисциплина.",
                       description="Очный отборочный этап. Результаты внесены организатором по итоговому протоколу.",
                       discipline=self.disc["ALG"], level=self.lv[0], format=Competition.Format.OFFLINE,
                       location="Махачкала, Технопарк ДГТУ", has_contest=False,
                       start_at=now - timedelta(days=430, hours=5), end_at=now - timedelta(days=430))
        self._manual(c, [(A[1], 780), (A[2], 720), (A[8], 650), (A[0], 540), (A[4], 500), (A[3], 410)])

        # 2) Межрегиональный хакатон (очный, ручные результаты)
        c = self._comp(title="Весенний хакатон по продуктовому программированию",
                       short_description="48 часов на разработку MVP по реальному кейсу от индустриальных партнёров.",
                       description="## О хакатоне\nКоманды разрабатывали цифровые сервисы для региона.\n\n- формат: очно\n- защита перед жюри\n- оценка по 100-балльной шкале",
                       discipline=self.disc["PROD"], level=self.lv[2], format=Competition.Format.OFFLINE,
                       location="Махачкала, Технопарк ДГТУ", has_contest=False,
                       start_at=now - timedelta(days=150, hours=48), end_at=now - timedelta(days=150))
        self._manual(c, [(A[4], 92), (A[0], 88), (A[10], 81), (A[5], 74), (A[13], 70), (A[7], 66), (A[11], 61), (A[12], 40)])

        # 3) Первенство (региональное, ручные)
        c = self._comp(title="Первенство Республики Дагестан среди школьников",
                       short_description="Личное первенство по алгоритмическому программированию, 5 задач, 5 часов.",
                       discipline=self.disc["ALG"], level=self.lv[3], format=Competition.Format.OFFLINE,
                       location="Каспийск, Лицей №1", has_contest=False,
                       start_at=now - timedelta(days=75, hours=5), end_at=now - timedelta(days=75))
        self._manual(c, [(A[1], 500), (A[11], 430), (A[3], 430), (A[5], 350), (A[7], 280), (A[9], 240), (A[13], 150)])

        # 4) ТЕСТОВЫЙ КОНТЕСТ (завершён, итоги подведены) — основной демо-сценарий
        c = self._comp(title="Тестовый контест по алгоритмическому программированию",
                       short_description="Демонстрационный онлайн-контест: три задачи на префиксные суммы, динамику и поиск в ширину.",
                       description=DESC_TEST, rules=RULES, discipline=self.disc["ALG"], level=self.lv[3],
                       start_at=now - timedelta(days=2, hours=3), end_at=now - timedelta(days=2), max_attempts=10)
        tA = self._task(c, 0, "Сумма на отрезке", ST_A, 100, input_spec=IN_A, output_spec=OUT_A,
                        sample_input="5 3\n1 2 3 4 5\n1 3\n2 5\n4 4", sample_output="6\n14\n4", limits="1 с · 256 МБ")
        tB = self._task(c, 1, "Максимальный подотрезок", ST_B, 100, input_spec="В первой строке n (1 ≤ n ≤ 2·10^5), во второй — n целых чисел по модулю не более 10^9.",
                        output_spec="Одно число — максимальная сумма непустого подотрезка.",
                        sample_input="6\n-2 1 -3 4 -1 2", sample_output="5", limits="1 с · 256 МБ")
        tC = self._task(c, 2, "Кратчайший путь в лабиринте", ST_C, 150, input_spec="n, m (1 ≤ n, m ≤ 1000), затем n строк по m символов: . — свободно, # — стена, S — старт, T — финиш.",
                        output_spec="Длина кратчайшего пути или -1.", sample_input="3 4\nS..#\n.#..\n...T", sample_output="5",
                        limits="2 с · 256 МБ", notes="Перемещаться можно только по четырём направлениям.")
        plan = [  # athlete, [(task, minute, score)...]
            (A[1], [(tA, 12, 100), (tB, 31, 100), (tC, 95, 150)]),
            (A[2], [(tA, 9, 100), (tB, 44, 60), (tB, 58, 100), (tC, 120, 150)]),
            (A[0], [(tA, 15, 100), (tB, 40, 100), (tC, 150, 90)]),
            (A[8], [(tA, 11, 100), (tB, 70, 100), (tC, 140, 60)]),
            (A[4], [(tA, 20, 40), (tA, 29, 100), (tB, 62, 100)]),
            (A[3], [(tA, 18, 100), (tB, 80, 100), (tC, 170, 0)]),
            (A[10], [(tA, 25, 100), (tB, 90, 50)]),
            (A[5], [(tA, 33, 100), (tB, 110, 40)]),
            (A[11], [(tA, 22, 100), (tC, 160, 30)]),
            (A[9], [(tA, 47, 70)]),
        ]
        for athlete, subs in plan:
            Registration.objects.create(competition=c, athlete=athlete)
            for task, minute, score in subs:
                code = {tA.pk: ("python", CODE_PY), tB.pk: ("cpp", CODE_CPP), tC.pk: ("python", CODE_BFS)}[task.pk]
                comment = "Отличное решение!" if score == task.max_score else ("Не учтены крайние случаи." if score else "Неверный ответ на тесте 3.")
                self._sub(c, task, athlete, minute, score, code, comment)
        Registration.objects.create(competition=c, athlete=A[12])  # зарегистрировался, но не решал
        self._publish(c)

        # 5) ИДЁТ СЕЙЧАС
        c = self._comp(title="Кубок Дагестана по программированию — онлайн-тур",
                       short_description="Личный онлайн-тур Кубка: четыре задачи разной сложности, ручная проверка жюри.",
                       description=DESC_CUP, rules=RULES, discipline=self.disc["ALG"], level=self.lv[2],
                       start_at=now - timedelta(minutes=50), end_at=now + timedelta(hours=3, minutes=10),
                       max_attempts=10, external_platform="Codeforces", external_url="https://codeforces.com/")
        t = [self._task(c, 0, "Шахматная доска", ST_CUP_A, 100, sample_input="3", sample_output="#.#\n.#.\n#.#"),
             self._task(c, 1, "Правильная скобочная последовательность", ST_CUP_B, 100, sample_input="(()())", sample_output="YES"),
             self._task(c, 2, "Горные маршруты", ST_CUP_C, 150, sample_input="3 3\n1 3 1\n1 5 1\n4 2 1", sample_output="7"),
             self._task(c, 3, "Сеть дорог", ST_CUP_D, 200, sample_input="4 5\n1 2 1\n2 3 4\n3 4 2\n1 4 5\n1 3 3", sample_output="6")]
        for a in A[:11]:
            Registration.objects.create(competition=c, athlete=a)
        self._sub(c, t[0], A[1], 7, 100, ("python", CODE_PY))
        self._sub(c, t[1], A[1], 21, 100, ("java", CODE_JAVA))
        self._sub(c, t[0], A[2], 9, 100)
        self._sub(c, t[0], A[3], 14, 70)
        self._sub(c, t[0], A[4], 12, 100)
        self._sub(c, t[1], A[4], 35)                    # на проверке
        self._sub(c, t[2], A[1], 44)                    # на проверке
        self._sub(c, t[0], A[8], 18)                    # на проверке
        self._sub(c, t[1], A[2], 30, None, ("java", CODE_JAVA))  # на проверке
        self._sub(c, t[0], A[0], 16, 100, ("python", CODE_PY), "Верно.")  # у демо-спортсмена одна задача решена

        # 6) СКОРО
        c = self._comp(title="Осенний отборочный контест ФСП РД",
                       short_description="Отбор в сборную республики на всероссийские соревнования. Регистрация открыта.",
                       description="Контест из трёх задач. Победители и призёры получают приглашение в сборную Республики Дагестан.",
                       rules=RULES, discipline=self.disc["ALG"], level=self.lv[3],
                       start_at=(now + timedelta(days=5)).replace(hour=11, minute=0), end_at=(now + timedelta(days=5)).replace(hour=15, minute=0),
                       registration_end=(now + timedelta(days=4)).replace(hour=23, minute=59), max_participants=200)
        for i, (ttl, st) in enumerate([("Разминка", "Выведите сумму двух чисел."), ("Жадный выбор", "Задача на сортировку и жадность."), ("Деревья", "Задача на обход дерева.")]):
            self._task(c, i, ttl, st)
        for a in A[1:7]:
            Registration.objects.create(competition=c, athlete=a)

        c = self._comp(title="Кибербезопасность: учебный CTF",
                       short_description="Командный учебный CTF для студентов вузов республики: web, crypto, forensics.",
                       discipline=self.disc["SEC"], level=self.lv[4],
                       start_at=(now + timedelta(days=12)).replace(hour=10, minute=0), end_at=(now + timedelta(days=12)).replace(hour=18, minute=0))
        for i, ttl in enumerate(["Web: забытый пароль", "Crypto: шифр Цезаря 2.0", "Forensics: потерянный файл"]):
            self._task(c, i, ttl, "Найдите флаг формата `FSP{...}` и отправьте его текстовым ответом.", 100)

        # 7) ЧЕРНОВИК
        c = self._comp(title="Зимняя школа олимпиадного программирования — вступительный контест",
                       short_description="Черновик: вступительные испытания в зимнюю школу.", is_published=False, published_at=None,
                       discipline=self.disc["ALG"], level=self.lv[4],
                       start_at=now + timedelta(days=40), end_at=now + timedelta(days=40, hours=3))
        self._task(c, 0, "Числа Фибоначчи", "Вычислите n-е число Фибоначчи по модулю 10^9+7.")

    def _manual(self, comp, pairs):
        for a, _ in pairs:
            Registration.objects.get_or_create(competition=comp, athlete=a)
        for a, score, place in assign_places(pairs):
            Result.objects.create(competition=comp, athlete=a, score=score, place=place, is_manual=True)
        self._publish(comp)

    # ------------------------------------------------------------------
    def _content(self):
        now = self.now
        news = [
            ("Итоги тестового контеста по алгоритмическому программированию", "Итоги", "Подведены итоги демонстрационного онлайн-контеста. Результаты уже в профилях участников и в рейтинге.", "Благодарим всех участников! Итоговая таблица и протокол доступны на странице соревнования.\n\n## Победители\n- 1 место — Магомедов Шамиль\n- 2 место — Алиева Патимат\n- 3 место — Иванов Алексей", 1, True),
            ("Стартовал онлайн-тур Кубка Дагестана", "Соревнования", "Участники уже отправляют решения. Жюри проверяет решения в режиме реального времени.", "Онлайн-тур продлится чуть больше четырёх часов. Предварительная таблица обновляется после каждой проверки.", 0, False),
            ("Открыта регистрация на осенний отборочный контест", "Анонсы", "Лучшие спортсмены войдут в сборную республики.", "Регистрация доступна всем спортсменам с профилем на платформе. Лимит — 200 участников.", 3, False),
            ("Федерация запускает платформу «ФСП Контест»", "Федерация", "Единая площадка для соревнований, результатов и рейтинга спортсменов.", "Платформа объединяет профили спортсменов, соревнования, результаты и рейтинг. Теперь контесты проводятся прямо на платформе: от публикации задач до появления результата в профиле.", 20, False),
            ("Новая методика рейтинга спортсменов", "Рейтинг", "Учитываются уровень соревнования, место, массовость, сила состава, разряд и давность.", "Подробное описание формулы опубликовано на странице рейтинга. Коэффициенты уровней и разрядов утверждены федерацией.", 25, False),
        ]
        for title, tag, ex, body, days, pinned in news:
            News.objects.create(title=title, tag=tag, excerpt=ex, body=body, is_pinned=pinned,
                                published_at=now - timedelta(days=days, hours=2), author=self.org)
        docs = [
            ("Положение о Кубке Республики Дагестан по спортивному программированию", "regulation", "Цели, сроки, порядок проведения и подведения итогов.", DOC_REG, ""),
            ("Положение о рейтинге спортсменов ФСП РД", "regulation", "Методика расчёта рейтинга и порядок подтверждения разрядов.", DOC_RATING, ""),
            ("Правила проведения онлайн-контестов", "rules", "Отправка решений, проверка, распределение мест.", RULES, ""),
            ("Кодекс честной игры", "rules", "Запрещённые действия и санкции.", DOC_FAIR, ""),
            ("Правила вида спорта «Спортивное программирование»", "official", "Официальные правила вида спорта (Минспорт России).", "Официальный текст правил вида спорта. Ознакомьтесь с актуальной редакцией на сайте Министерства спорта РФ.", "https://www.minsport.gov.ru/"),
            ("Единая всероссийская спортивная классификация", "official", "Нормы и требования для присвоения разрядов.", "Требования для присвоения спортивных разрядов и званий по спортивному программированию.", "https://www.minsport.gov.ru/"),
            ("Алгоритмы и структуры данных: конспекты", "material", "Сборник статей по алгоритмам для подготовки к олимпиадам.", "", "https://cp-algorithms.com/"),
            ("Тренировочные задачи Codeforces", "material", "Архив задач с разбором по уровню сложности.", "", "https://codeforces.com/problemset"),
            ("Informatics.msk.ru — школьный архив задач", "material", "Задачи по темам для начинающих спортсменов.", "", "https://informatics.msk.ru/"),
        ]
        for i, (t, cat, d, body, url) in enumerate(docs):
            Document.objects.create(title=t, category=cat, description=d, body=body, url=url, order=i,
                                    published_at=now - timedelta(days=30 - i))
        faq = [
            ("Регистрация", "Как зарегистрироваться на соревнование?", "Создайте профиль спортсмена, откройте страницу соревнования и нажмите **«Зарегистрироваться»**. Заявка сразу появится у организатора."),
            ("Регистрация", "Можно ли отозвать заявку?", "Да, до старта соревнования — кнопкой «Отозвать заявку» на странице соревнования."),
            ("Контесты", "Как отправить решение?", "Во время тура откройте задачу и вставьте код в редактор или загрузите файл (до 256 КБ). Нажмите **«Отправить»** или `Ctrl+Enter`."),
            ("Контесты", "Как проверяются решения?", "Решения проверяет организатор вручную и выставляет баллы. По каждой задаче засчитывается лучшая попытка."),
            ("Контесты", "Как распределяются места при равенстве баллов?", "Выше участник с меньшим суммарным временем получения лучших баллов. При полном равенстве место делится."),
            ("Рейтинг", "Как рассчитывается рейтинг?", "R = Q + Σ P·D. Подробная формула — на странице **Рейтинг → Методика**."),
            ("Рейтинг", "Почему мой разряд не учитывается?", "Бонус разряда начисляется после подтверждения организатором. Статус виден в профиле."),
            ("Безопасность", "Кто видит мои персональные данные?", "Email и дату рождения видит только организатор. В рейтинге публикуются ФИО, город, разряд и результаты. Учебное заведение можно скрыть."),
            ("Безопасность", "Как удалить аккаунт?", "В разделе **Настройки → Мои данные**. Там же можно выгрузить все свои данные в JSON."),
        ]
        for i, (cat, q, a) in enumerate(faq):
            FAQ.objects.create(category=cat, question=q, answer=a, order=i)


# ============================================================== тексты
RULES = """## Общие положения
- Соревнование проводится в личном зачёте.
- Решения принимаются только в период проведения тура.
- Каждое решение проверяется организатором (жюри) вручную.

## Отправка решений
- Решение вводится в редакторе на странице задачи или загружается файлом (до 256 КБ).
- Количество попыток по каждой задаче ограничено; засчитывается **лучшая** проверенная попытка.
- Между отправками действует пауза 10 секунд.

## Подведение итогов
- Места распределяются по сумме баллов.
- При равенстве баллов выше участник с меньшим суммарным временем получения лучших баллов.
- При полном равенстве участники делят место.

## Честная игра
- Запрещено использовать чужие решения, передавать своё решение другим участникам и использовать несколько аккаунтов.
- Нарушение правил ведёт к дисквалификации."""

DESC_TEST = """Демонстрационный контест платформы **ФСП Контест**.

## Формат
- 3 задачи, 3 часа
- ручная проверка жюри
- итоговая таблица и рейтинговые очки

> Контест используется для демонстрации полного сценария: от создания соревнования до результата в профиле спортсмена."""

DESC_CUP = """Онлайн-тур **Кубка Республики Дагестан** по спортивному программированию.

## Что нужно знать
- 4 задачи разной сложности, суммарно 550 баллов
- решения проверяются жюри в течение тура
- предварительная таблица обновляется после каждой проверки"""

ST_A = """Дан массив из **n** целых чисел и **q** запросов. Каждый запрос — пара индексов `l` и `r`. Для каждого запроса выведите сумму элементов массива с индексами от `l` до `r` включительно.

Используйте префиксные суммы, чтобы отвечать на каждый запрос за O(1)."""
IN_A = "В первой строке — n и q (1 ≤ n, q ≤ 2·10^5). Во второй — n чисел a_i (|a_i| ≤ 10^9). Далее q строк с парами l, r (1 ≤ l ≤ r ≤ n)."
OUT_A = "Для каждого запроса выведите сумму на отрезке в отдельной строке."
ST_B = """Дан массив целых чисел. Найдите непустой подотрезок (последовательность подряд идущих элементов) с **максимальной суммой**.

Подсказка: известен алгоритм, решающий задачу за один проход по массиву."""
ST_C = """Лабиринт задан прямоугольной таблицей **n × m**. Найдите длину кратчайшего пути из клетки `S` в клетку `T`. За один шаг можно перейти в соседнюю по стороне свободную клетку.

Если пути нет, выведите `-1`."""
ST_CUP_A = "По заданному **n** выведите шахматную доску n × n из символов `#` и `.`, левая верхняя клетка — `#`."
ST_CUP_B = "Дана строка из круглых скобок. Определите, является ли она правильной скобочной последовательностью. Выведите `YES` или `NO`."
ST_CUP_C = "Дана таблица высот n × m. Турист идёт из левого верхнего угла в правый нижний, перемещаясь только вправо или вниз. Найдите минимальную сумму высот на пути."
ST_CUP_D = "Дан взвешенный неориентированный граф из n городов и m дорог. Выберите набор дорог минимального суммарного веса, чтобы из любого города можно было добраться в любой (минимальное остовное дерево)."

DOC_REG = """## 1. Общие положения
Кубок проводится Федерацией спортивного программирования Республики Дагестан с целью популяризации вида спорта и выявления сильнейших спортсменов.

## 2. Сроки и место проведения
- онлайн-тур — на платформе «ФСП Контест»;
- финал — очно, Технопарк ДГТУ, г. Махачкала.

## 3. Участники
К участию допускаются спортсмены, зарегистрированные на платформе и подавшие заявку в установленный срок.

## 4. Подведение итогов
Победители и призёры определяются по сумме баллов. Результаты учитываются в рейтинге спортсменов с коэффициентом уровня соревнования."""

DOC_RATING = """## Формула
**R = Q + Σ P · D**, где Q — бонус подтверждённого разряда, P — очки за результат, D — коэффициент давности.

## Очки за результат
P = 100 · (N − M + 1) / N · K_ур · K_N · K_поля

- K_ур — коэффициент уровня соревнования (Чемпионат России — 2.0, всероссийские — 1.6, межрегиональные — 1.3, региональные — 1.0, муниципальные — 0.7);
- K_N = 1 + 0.25 · lg N — массовость;
- K_поля — сила состава по разрядам участников.

## Давность
D = 0.5^(t/365) — вес результата уменьшается вдвое каждый год."""

DOC_FAIR = """## Запрещено
- использовать чужой код и решения других участников;
- передавать своё решение во время тура;
- создавать несколько учётных записей;
- пытаться нарушить работу платформы.

## Санкции
Аннулирование результата, дисквалификация, исключение из рейтинга."""
