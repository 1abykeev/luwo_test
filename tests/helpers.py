"""Look things up in the demo world by name, so tests don't hard-code ids."""

from seed.world import build_world

WORLD = build_world()

LYCEUM, GYMNASIUM, SCHOOL12 = "Лицей №1", "Гимназия №5", "Школа №12"


def user_id(email: str) -> int:
    return next(u.id for u in WORLD.users if u.email == email)


def school_id(name: str) -> int:
    return next(s.id for s in WORLD.schools if s.name == name)


def class_id(school: str, name: str) -> int:
    return next(c.id for c in WORLD.classes if c.school_id == school_id(school) and c.name == name)


def student_id(school: str, class_name: str, full_name: str) -> int:
    """Id of a student as seeded (before the demo transfers)."""
    # Transferred students start in a different class than they end in, so match on name + school.
    matches = [s for s in WORLD.students if s.school_id == school_id(school) and s.full_name == full_name]
    in_class = [s for s in matches if s.class_name == class_name]
    return (in_class or matches)[0].id


def teacher_id(email: str) -> int:
    return user_id(email)
