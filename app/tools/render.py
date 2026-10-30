"""Turn service results into plain dicts: for the model (as JSON) and for the app (as blocks)."""

from app.services.views import HistoryEvent, StudentFinding, StudentHit


def student_dict(student, school: str | None = None) -> dict:
    data = {
        "id": student.id,
        "full_name": student.full_name,
        "class": student.class_name,
        "status": student.status.value,
    }
    if school is not None:
        data["school"] = school
    return data


def hit_dict(hit: StudentHit) -> dict:
    return student_dict(hit.student, hit.school_name)


def teacher_dict(teacher) -> dict:
    return {"id": teacher.id, "full_name": teacher.full_name}


def event_dict(event: HistoryEvent) -> dict:
    return {
        "action": event.action,
        "date": event.at.date().isoformat() if event.at else None,
        "from_class": event.from_class,
        "to_class": event.to_class,
    }


def finding_dict(finding: StudentFinding) -> dict:
    return {
        "student_id": finding.student_id,
        "full_name": finding.full_name,
        "state": finding.state,
        "current_class": finding.current_class,
        "history": [event_dict(e) for e in finding.events],
    }
