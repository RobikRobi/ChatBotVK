import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook


ROOM_RE = re.compile(r"\s*\d+(?:[\\/]\d+)*$")
DAY_NAMES = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница")


@dataclass(frozen=True)
class ScheduleData:
    classes: list[str]
    grades: dict[str, list[str]]
    subjects: list[str]


def _value(cell):
    return "" if cell is None else str(cell).strip()


def _normalize_subject(text: str) -> str:
    text = " ".join(text.replace("\\\n", " ").replace("\n", " ").split())
    text = ROOM_RE.sub("", text).strip()
    replacements = {
        "Английский яз.": "Английский язык",
        "Индивид.проект": "Индивидуальный проект",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def load_schedule(path: Path) -> ScheduleData:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook.active
    rows = [[_value(cell.value) for cell in row] for row in sheet.iter_rows()]

    header = next((row for row in rows if len(row) > 2 and row[1] == "Звонки"), None)
    if not header:
        raise RuntimeError("Не удалось найти строку с классами в расписании.")

    classes = [name for name in header[2:] if name]
    grades: dict[str, list[str]] = {}
    for class_name in classes:
        grade = re.match(r"\d+", class_name)
        if grade:
            grades.setdefault(grade.group(0), []).append(class_name)

    subjects = set()
    class_set = set(classes)
    for row in rows:
        if len(row) < 3 or row[1] == "Звонки":
            continue
        for cell in row[2:]:
            if not cell or cell in class_set or cell in DAY_NAMES:
                continue
            for part in re.split(r"\s*/\s*|\s*\\\s*", cell):
                subject = _normalize_subject(part)
                if subject and subject not in class_set:
                    subjects.add(subject)

    return ScheduleData(
        classes=classes,
        grades={grade: sorted(names) for grade, names in sorted(grades.items(), key=lambda item: int(item[0]))},
        subjects=sorted(subjects),
    )
