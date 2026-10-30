"""The demo world as plain domain objects. No database code in here.

Both the Postgres seed script and the in-memory adapter load from this one builder,
so tests run on identical data against both.

Test scenarios built into this data:
- same class name in every school (4А exists three times)    -> isolation checks
- two "Амир" in Лицей №1 / 4А                                 -> "which Amir?"
- three "Алина Смирнова" (two in Лицей №1, one in Гимназия)   -> duplicates
- "Амир Касымов" also in Гимназия №5                          -> cross-school namesake
- Эрмек Бакиров and Станислав Попов are deactivated           -> inactive records
- Алина Иманова moved 3А -> 3Б (same teacher leads both)
- Алина Назарова moved 4А -> 4Б (4Б is led by a different teacher)
- a removed teacher, classes without a teacher, a teacher without classes
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from app.domain.models import (
    ChangeEntry,
    Role,
    School,
    SchoolClass,
    Student,
    StudentStatus,
    User,
)

DEMO_PASSWORD = "demo1234"

# school -> class -> (teacher emails, students); a leading "!" marks a deactivated student
SCHOOLS = {
    "Лицей №1": {
        "3А": (["bakyt@luwo.test"], ["Алина Смирнова", "Данияр Исаков", "Мээрим Асанова", "Тимур Ли", "Адиля Кадырова", "Руслан Мамытов"]),
        "3Б": (["bakyt@luwo.test"], ["Алина Смирнова", "Эмир Сыдыков", "Айзада Токоева", "Артём Волков", "Сезим Абдыкадырова"]),
        "4А": (["aigul@luwo.test"], ["Амир Касымов", "Амир Жумаев", "Бермет Алиева", "Касым Усенов", "Жанара Сатыбалдиева", "!Эрмек Бакиров"]),
        "4Б": (["nurlan@luwo.test"], ["Нурсултан Абдрахманов", "Элина Мусаева", "Тилек Орозов", "Аселя Бекова"]),
    },
    "Гимназия №5": {
        "3А": (["elena@luwo.test"], ["Алина Смирнова", "Иван Кузнецов", "София Морозова", "Эльдар Рахимов", "Амира Сулайманова"]),
        "3Б": ([], ["Артур Белов", "Лейла Хасанова", "Максим Орлов", "Асель Курманова"]),
        "4А": (["marat@luwo.test"], ["Амир Касымов", "Ольга Новикова", "Бекзат Мойдунов", "Камила Эсенова", "!Станислав Попов"]),
    },
    "Школа №12": {
        "4А": (["dinara@luwo.test"], ["Айбек Сабиров", "Гульнара Темирова", "Данил Фролов", "Чолпон Жолдошева"]),
        "4Б": ([], ["Азамат Эркинбеков", "Мадина Раимова", "Арслан Кенжебаев"]),
    },
}

# (email, full name, role, school or None, is_active)
USERS = [
    ("root@luwo.test", "Главный администратор", Role.SUPERADMIN, None, True),
    ("admin1@luwo.test", "Салтанат Рыскулова", Role.SCHOOL_ADMIN, "Лицей №1", True),
    ("admin2@luwo.test", "Виктор Андреев", Role.SCHOOL_ADMIN, "Гимназия №5", True),
    ("admin3@luwo.test", "Жылдыз Эсенова", Role.SCHOOL_ADMIN, "Школа №12", True),
    ("bakyt@luwo.test", "Бакыт Осмонов", Role.TEACHER, "Лицей №1", True),
    ("aigul@luwo.test", "Айгуль Садыкова", Role.TEACHER, "Лицей №1", True),
    ("nurlan@luwo.test", "Нурлан Ибраев", Role.TEACHER, "Лицей №1", True),
    ("gulmira@luwo.test", "Гульмира Дюшеева", Role.TEACHER, "Лицей №1", False),  # removed
    ("elena@luwo.test", "Елена Петрова", Role.TEACHER, "Гимназия №5", True),
    ("marat@luwo.test", "Марат Жумабеков", Role.TEACHER, "Гимназия №5", True),
    ("sergey@luwo.test", "Сергей Лебедев", Role.TEACHER, "Гимназия №5", True),  # no classes
    ("dinara@luwo.test", "Динара Токтогулова", Role.TEACHER, "Школа №12", True),
]

# Students that start in one class and are then transferred: (school, name, from, to, days ago)
TRANSFERS = [
    ("Лицей №1", "Алина Иманова", "3А", "3Б", 5),
    ("Лицей №1", "Алина Назарова", "4А", "4Б", 3),
]

DEACTIVATED_DAYS_AGO = {"Эрмек Бакиров": 10, "Станислав Попов": 20}


@dataclass
class World:
    schools: list[School]
    users: list[User]
    classes: list[SchoolClass]
    class_teachers: list[tuple[int, int]]  # (class_id, teacher_id)
    students: list[Student]
    history: list[ChangeEntry]


def build_world(password_hash: str | None = None, now: datetime | None = None) -> World:
    now = now or datetime.now(timezone.utc)
    schools = [School(id=i, name=name) for i, name in enumerate(SCHOOLS, start=1)]
    school_id = {s.name: s.id for s in schools}

    users = [
        User(
            id=i, email=email, full_name=name, role=role,
            school_id=school_id[school] if school else None,
            is_active=active, password_hash=password_hash,
        )
        for i, (email, name, role, school, active) in enumerate(USERS, start=1)
    ]
    user_id = {u.email: u.id for u in users}
    admin_of = {u.school_id: u.id for u in users if u.role == Role.SCHOOL_ADMIN}

    classes: list[SchoolClass] = []
    class_teachers: list[tuple[int, int]] = []
    students: list[Student] = []
    class_id = {}  # (school name, class name) -> id

    def add_student(school_name: str, class_name: str, full_name: str, status: StudentStatus) -> None:
        students.append(Student(
            id=len(students) + 1, school_id=school_id[school_name],
            class_id=class_id[(school_name, class_name)], class_name=class_name,
            full_name=full_name, status=status,
        ))

    for school_name, class_defs in SCHOOLS.items():
        for class_name, (teacher_emails, names) in class_defs.items():
            cls = SchoolClass(id=len(classes) + 1, school_id=school_id[school_name], name=class_name)
            classes.append(cls)
            class_id[(school_name, class_name)] = cls.id
            class_teachers += [(cls.id, user_id[email]) for email in teacher_emails]
            for raw in names:
                status = StudentStatus.INACTIVE if raw.startswith("!") else StudentStatus.ACTIVE
                add_student(school_name, class_name, raw.lstrip("!"), status)

    for school_name, full_name, from_class, _, _ in TRANSFERS:
        add_student(school_name, from_class, full_name, StudentStatus.ACTIVE)

    history: list[ChangeEntry] = []

    def log(action, entity_type, entity_id, school, before, after, days_ago, actor=None):
        history.append(ChangeEntry(
            action=action, entity_type=entity_type, entity_id=entity_id, school_id=school,
            actor_user_id=actor, source="seed", before=before, after=after,
            at=now - timedelta(days=days_ago),
        ))

    for s in students:
        log("student_added", "student", s.id, s.school_id, None,
            {"class_id": s.class_id, "class_name": s.class_name, "status": "active"}, 60)

    for s in students:
        if s.status == StudentStatus.INACTIVE:
            log("student_deactivated", "student", s.id, s.school_id,
                {"class_id": s.class_id, "class_name": s.class_name, "status": "active"},
                {"class_id": s.class_id, "class_name": s.class_name, "status": "inactive"},
                DEACTIVATED_DAYS_AGO[s.full_name], admin_of[s.school_id])

    for school_name, full_name, from_class, to_class, days_ago in TRANSFERS:
        index = next(i for i, s in enumerate(students) if s.full_name == full_name)
        s = students[index]
        to_id = class_id[(school_name, to_class)]
        log("student_transferred", "student", s.id, s.school_id,
            {"class_id": s.class_id, "class_name": from_class},
            {"class_id": to_id, "class_name": to_class}, days_ago, admin_of[s.school_id])
        students[index] = replace(s, class_id=to_id, class_name=to_class)

    for u in users:
        if not u.is_active:
            log("teacher_removed", "teacher", u.id, u.school_id,
                {"is_active": True}, {"is_active": False}, 15, admin_of[u.school_id])

    return World(schools, users, classes, class_teachers, students, history)
