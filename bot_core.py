from dataclasses import dataclass
from typing import Iterable


ROLE_LABELS = {
    "student": "Ученик",
    "parent": "Родитель",
    "teacher": "Учитель",
}

KEYBOARD_ROLE = "role"
KEYBOARD_GRADE = "grade"
KEYBOARD_CLASS = "class"
KEYBOARD_MAIN = "main"


@dataclass(frozen=True)
class BotReply:
    text: str
    keyboard: str | None = None
    keyboard_options: tuple[str, ...] = ()


def parse_role(text):
    normalized = text.strip().lower()
    if normalized in ("ученик", "школьник"):
        return "student"
    if normalized in ("родитель", "мама", "папа"):
        return "parent"
    if normalized in ("учитель", "преподаватель", "педагог"):
        return "teacher"
    return None


def format_numbered(items: Iterable[str]):
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def parse_numbers(text, max_number):
    numbers = set()
    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            left, right = chunk.split("-", 1)
            if left.strip().isdigit() and right.strip().isdigit():
                start, end = int(left), int(right)
                numbers.update(range(min(start, end), max(start, end) + 1))
            continue
        if chunk.isdigit():
            numbers.add(int(chunk))
    return sorted(number for number in numbers if 1 <= number <= max_number)


def ask_role():
    return BotReply(
        "Привет! Выберите роль: ученик, родитель или учитель.",
        keyboard=KEYBOARD_ROLE,
    )


def ask_grade(schedule):
    return BotReply(
        "Выберите параллель класса.",
        keyboard=KEYBOARD_GRADE,
        keyboard_options=tuple(schedule.grades.keys()),
    )


def ask_teacher_subjects(schedule):
    return BotReply(
        "Выберите предметы, которые вы ведёте.\n"
        "Напишите номера через запятую, например: 1, 4, 7.\n\n"
        f"{format_numbered(schedule.subjects)}",
    )


def ask_teacher_classes(schedule):
    return BotReply(
        "Теперь выберите классы, в которых вы ведёте уроки.\n"
        "Напишите номера через запятую, например: 2, 5, 9.\n\n"
        f"{format_numbered(schedule.classes)}",
    )


def profile_text(profile):
    role = ROLE_LABELS.get(profile.get("role"), "Не выбрана")
    if profile.get("role") in ("student", "parent"):
        return f"Ваш профиль:\nРоль: {role}\nКласс: {profile.get('class_name', 'не выбран')}"
    if profile.get("role") == "teacher":
        subjects = ", ".join(profile.get("subjects", [])) or "не выбраны"
        classes = ", ".join(profile.get("classes", [])) or "не выбраны"
        return f"Ваш профиль:\nРоль: {role}\nПредметы: {subjects}\nКлассы: {classes}"
    return "Профиль пока не заполнен."


def format_schedule(title, lessons, show_class=True):
    if not lessons:
        return f"{title}\n\nРасписание не найдено."

    lines = [title]
    current_day = None
    for lesson in lessons:
        if lesson.day != current_day:
            current_day = lesson.day
            lines.append("")
            lines.append(current_day)
        class_prefix = f"{lesson.class_name}: " if show_class and lesson.class_name else ""
        lines.append(f"{lesson.time} - {class_prefix}{lesson.subject or '-'}")
    return "\n".join(lines)


def schedule_text(profile, schedule):
    role = profile.get("role")
    if role in ("student", "parent"):
        class_name = profile.get("class_name")
        if not class_name:
            return "Сначала выберите класс через «Начать заново»."
        lessons = schedule.lessons_for_class(class_name)
        return format_schedule(f"Расписание для {class_name}", lessons, show_class=False)

    if role == "teacher":
        subjects = profile.get("subjects", [])
        classes = profile.get("classes", [])
        if not subjects or not classes:
            return "Сначала выберите предметы и классы через «Начать заново»."
        lessons = schedule.lessons_for_teacher(subjects, classes)
        return format_schedule("Ваши уроки", lessons)

    return "Сначала выберите роль через «Начать заново»."


def profile_ready(profile):
    return BotReply(
        f"Готово, сохранил профиль.\n\n{profile_text(profile)}\n\n"
        "Нажмите «Расписание», чтобы получить уроки.",
        keyboard=KEYBOARD_MAIN,
    )


def handle_message(storage, schedule, user_id, text):
    text = (text or "").strip()
    user = storage.get_user(user_id)
    text_lower = text.lower()

    if not text or text_lower in ("/start", "start", "начать", "начать заново"):
        storage.reset_user(user_id)
        return ask_role()

    if text_lower == "мой профиль":
        return BotReply(profile_text(user.get("profile", {})), keyboard=KEYBOARD_MAIN)

    if text_lower in ("расписание", "моё расписание", "мое расписание"):
        return BotReply(schedule_text(user.get("profile", {}), schedule), keyboard=KEYBOARD_MAIN)

    if text_lower == "назад":
        role = user.get("profile", {}).get("role")
        if role in ("student", "parent"):
            user["step"] = "grade"
            storage.update_user(user_id, user)
            return ask_grade(schedule)

    step = user.get("step", "role")
    profile = user.setdefault("profile", {})

    if step == "role":
        role = parse_role(text)
        if not role:
            return ask_role()
        profile.clear()
        profile["role"] = role
        if role in ("student", "parent"):
            user["step"] = "grade"
            storage.update_user(user_id, user)
            return ask_grade(schedule)

        user["step"] = "teacher_subjects"
        storage.update_user(user_id, user)
        return ask_teacher_subjects(schedule)

    if step == "grade":
        grade = "".join(ch for ch in text if ch.isdigit())
        if grade not in schedule.grades:
            return ask_grade(schedule)
        profile["grade"] = grade
        user["step"] = "class_letter"
        storage.update_user(user_id, user)
        return BotReply(
            "Выберите букву класса.",
            keyboard=KEYBOARD_CLASS,
            keyboard_options=tuple(schedule.grades[grade]),
        )

    if step == "class_letter":
        grade = profile.get("grade")
        options = schedule.grades.get(grade, [])
        normalized = text_lower.replace(" ", "")
        selected = next((name for name in options if name.lower() == normalized), None)
        if not selected and grade:
            selected = next((name for name in options if name.lower().replace(grade, "") == normalized), None)
        if not selected:
            return BotReply(
                "Не нашёл такой класс. Выберите вариант из списка.",
                keyboard=KEYBOARD_CLASS,
                keyboard_options=tuple(options),
            )
        profile["class_name"] = selected
        user["step"] = "done"
        storage.update_user(user_id, user)
        return profile_ready(profile)

    if step == "teacher_subjects":
        numbers = parse_numbers(text, len(schedule.subjects))
        if not numbers:
            return ask_teacher_subjects(schedule)
        profile["subjects"] = [schedule.subjects[number - 1] for number in numbers]
        user["step"] = "teacher_classes"
        storage.update_user(user_id, user)
        return ask_teacher_classes(schedule)

    if step == "teacher_classes":
        numbers = parse_numbers(text, len(schedule.classes))
        if not numbers:
            return ask_teacher_classes(schedule)
        profile["classes"] = [schedule.classes[number - 1] for number in numbers]
        user["step"] = "done"
        storage.update_user(user_id, user)
        return profile_ready(profile)

    return BotReply(
        "Нажмите «Расписание», чтобы получить уроки.",
        keyboard=KEYBOARD_MAIN,
    )
