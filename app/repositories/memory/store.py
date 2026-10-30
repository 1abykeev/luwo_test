from dataclasses import dataclass, field, replace

from app.domain.models import ChangeEntry, PendingAction, School, SchoolClass, Student, User


@dataclass
class MemoryData:
    """Everything the in-memory adapter keeps, as plain dicts and lists."""

    schools: dict[int, School] = field(default_factory=dict)
    users: dict[int, User] = field(default_factory=dict)
    classes: dict[int, SchoolClass] = field(default_factory=dict)
    class_teachers: set[tuple[int, int]] = field(default_factory=set)  # (class_id, teacher_id)
    students: dict[int, Student] = field(default_factory=dict)
    history: list[ChangeEntry] = field(default_factory=list)
    pending: dict[str, PendingAction] = field(default_factory=dict)


class MemoryStore:
    """Owns the committed data. A unit of work edits a copy and publishes it on commit."""

    def __init__(self, data: MemoryData | None = None):
        self.data = data or MemoryData()


def load_demo_world(password_hash: str | None = None) -> MemoryStore:
    from seed.world import build_world

    world = build_world(password_hash=password_hash)
    return MemoryStore(
        MemoryData(
            schools={s.id: s for s in world.schools},
            users={u.id: u for u in world.users},
            classes={c.id: c for c in world.classes},
            class_teachers=set(world.class_teachers),
            students={s.id: s for s in world.students},
            history=[replace(e, id=i) for i, e in enumerate(world.history, start=1)],
        )
    )
