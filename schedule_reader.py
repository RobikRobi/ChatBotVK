import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook


ROOM_RE = re.compile(r"\s*\d+(?:[\\/]\d+)*$")
DAY_NAMES = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница")


@dataclass(frozen=True)
class Lesson:
    day: str
    time: str
    class_name: str
    subject: str


@dataclass(frozen=True)
class ScheduleData:
    classes: list[str]
    grades: dict[str, list[str]]
    subjects: list[str]
    lessons: list[Lesson]

    def lessons_for_class(self, class_name: str) -> list[Lesson]:
        return [lesson for lesson in self.lessons if lesson.class_name == class_name and lesson.subject]

    def lessons_for_teacher(self, subjects: list[str], classes: list[str]) -> list[Lesson]:
        subject_set = set(subjects)
        class_set = set(classes)
        result = []
        for lesson in self.lessons:
            if lesson.class_name not in class_set or not lesson.subject:
                continue
            lesson_subjects = subjects_from_cell(lesson.subject)
            if subject_set.intersection(lesson_subjects):
                result.append(lesson)
        return result


def _value(cell):
    return "" if cell is None else str(cell).strip()


def normalize_subject(text: str) -> str:
    text = " ".join(text.replace("\\\n", " ").replace("\n", " ").split())
    replacements = {
        "Английский яз.": "Английский язык",
        "Индивид.проект": "Индивидуальный проект",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return ROOM_RE.sub("", text).strip()


def subjects_from_cell(text: str) -> list[str]:
    subjects = []
    for part in re.split(r"\s*/\s*|\s*\\\s*", text):
        subject = normalize_subject(part)
        if subject and not subject.isdigit():
            subjects.append(subject)
    return subjects


def _build_grades(classes: list[str]) -> dict[str, list[str]]:
    grades: dict[str, list[str]] = {}
    for class_name in classes:
        grade = re.match(r"\d+", class_name)
        if grade:
            grades.setdefault(grade.group(0), []).append(class_name)
    return {
        grade: sorted(names)
        for grade, names in sorted(grades.items(), key=lambda item: int(item[0]))
    }


def load_schedule(path: Path) -> ScheduleData:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook.active
    rows = [[_value(cell.value) for cell in row] for row in sheet.iter_rows()]

    header_indexes = [
        index for index, row in enumerate(rows)
        if len(row) > 2 and row[1] == "Звонки"
    ]
    if not header_indexes:
        raise RuntimeError("Не удалось найти строку с классами в расписании.")

    classes = [name for name in rows[header_indexes[0]][2:] if name]
    class_set = set(classes)
    subjects = set()
    lessons: list[Lesson] = []

    for block_number, header_index in enumerate(header_indexes):
        day = DAY_NAMES[block_number] if block_number < len(DAY_NAMES) else f"День {block_number + 1}"
        header = rows[header_index]
        next_header = header_indexes[block_number + 1] if block_number + 1 < len(header_indexes) else len(rows)

        for row in rows[header_index + 1:next_header]:
            if len(row) < 3 or not row[1]:
                continue
            lesson_time = row[1]
            for col_index, class_name in enumerate(header[2:], start=2):
                if not class_name or class_name not in class_set:
                    continue
                cell_text = row[col_index] if col_index < len(row) else ""
                if cell_text:
                    subjects.update(subjects_from_cell(cell_text))
                lessons.append(
                    Lesson(
                        day=day,
                        time=lesson_time,
                        class_name=class_name,
                        subject=cell_text,
                    )
                )

    return ScheduleData(
        classes=classes,
        grades=_build_grades(classes),
        subjects=sorted(subjects),
        lessons=lessons,
    )
