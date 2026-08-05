import random
import sys

from config import SCHEDULE_FILE, USERS_FILE, VK_GROUP_ID, VK_TOKEN
from schedule_reader import load_schedule
from storage import JsonStorage

try:
    import vk_api
    from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
except ModuleNotFoundError:
    vk_api = None
    VkBotEventType = None
    VkBotLongPoll = None
    VkKeyboard = None
    VkKeyboardColor = None


ROLE_LABELS = {
    "student": "Ученик",
    "parent": "Родитель",
    "teacher": "Учитель",
}


def make_keyboard(rows, one_time=False):
    if VkKeyboard is None:
        return None
    keyboard = VkKeyboard(one_time=one_time)
    for row_index, row in enumerate(rows):
        if row_index:
            keyboard.add_line()
        for text, color in row:
            keyboard.add_button(text, color=color)
    return keyboard.get_keyboard()


def role_keyboard():
    return make_keyboard(
        [[
            ("Ученик", VkKeyboardColor.PRIMARY),
            ("Родитель", VkKeyboardColor.PRIMARY),
            ("Учитель", VkKeyboardColor.PRIMARY),
        ]],
        one_time=True,
    )


def grade_keyboard(grades):
    rows = []
    current = []
    for grade in grades:
        current.append((grade, VkKeyboardColor.SECONDARY))
        if len(current) == 4:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([("Начать заново", VkKeyboardColor.NEGATIVE)])
    return make_keyboard(rows)


def class_keyboard(classes):
    rows = []
    current = []
    for class_name in classes:
        current.append((class_name, VkKeyboardColor.SECONDARY))
        if len(current) == 4:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([("Назад", VkKeyboardColor.SECONDARY), ("Начать заново", VkKeyboardColor.NEGATIVE)])
    return make_keyboard(rows)


def main_keyboard():
    return make_keyboard(
        [
            [("Расписание", VkKeyboardColor.POSITIVE), ("Расписание на неделю", VkKeyboardColor.PRIMARY)],
            [("Мой профиль", VkKeyboardColor.PRIMARY)],
            [("Начать заново", VkKeyboardColor.NEGATIVE)],
        ]
    )


def send(vk, peer_id, text, keyboard=None):
    params = {
        "peer_id": peer_id,
        "message": text,
        "random_id": random.randint(1, 2_147_483_647),
    }
    if keyboard:
        params["keyboard"] = keyboard
    vk.messages.send(**params)


def send_long(vk, peer_id, text, keyboard=None, limit=3500):
    parts = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                parts.append(current)
            current = line
        else:
            current = candidate
    if current:
        parts.append(current)

    for index, part in enumerate(parts):
        send(vk, peer_id, part, keyboard if index == len(parts) - 1 else None)


def parse_role(text):
    normalized = text.strip().lower()
    if normalized in ("ученик", "школьник"):
        return "student"
    if normalized in ("родитель", "мама", "папа"):
        return "parent"
    if normalized in ("учитель", "преподаватель", "педагог"):
        return "teacher"
    return None


def format_numbered(items):
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


def ask_role(vk, peer_id):
    send(
        vk,
        peer_id,
        "Привет! Выберите роль: ученик, родитель или учитель.",
        role_keyboard(),
    )


def ask_grade(vk, peer_id, schedule):
    send(
        vk,
        peer_id,
        "Выберите параллель класса.",
        grade_keyboard(schedule.grades.keys()),
    )


def ask_teacher_subjects(vk, peer_id, schedule):
    send(
        vk,
        peer_id,
        "Выберите предметы, которые вы ведёте.\n"
        "Напишите номера через запятую, например: 1, 4, 7.\n\n"
        f"{format_numbered(schedule.subjects)}",
    )


def ask_teacher_classes(vk, peer_id, schedule):
    send(
        vk,
        peer_id,
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


def format_weekly_schedule(title, lessons, show_class=True):
    """Форматирует расписание на неделю с группировкой по дням."""
    if not lessons:
        return f"{title}\n\nРасписание не найдено."

    days_order = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    lessons_by_day = {}
    for lesson in lessons:
        lessons_by_day.setdefault(lesson.day, []).append(lesson)

    lines = [title]
    for day in days_order:
        day_lessons = lessons_by_day.get(day, [])
        if not day_lessons:
            continue
        lines.append("")
        lines.append(f"📅 {day}")
        for lesson in sorted(day_lessons, key=lambda x: x.time):
            class_prefix = f"{lesson.class_name}: " if show_class and lesson.class_name else ""
            subject_text = lesson.subject or '-'
            lines.append(f"  {lesson.time} - {class_prefix}{subject_text}")

    if len(lines) == 1:
        lines.append("\nРасписание не найдено.")

    return "\n".join(lines)


def schedule_text(profile, schedule, weekly=False):
    role = profile.get("role")
    if role in ("student", "parent"):
        class_name = profile.get("class_name")
        if not class_name:
            return "Сначала выберите класс через «Начать заново»."
        lessons = schedule.lessons_for_class(class_name)
        if weekly:
            return format_weekly_schedule(f"Расписание для {class_name}", lessons, show_class=False)
        return format_schedule(f"Расписание для {class_name}", lessons, show_class=False)

    if role == "teacher":
        subjects = profile.get("subjects", [])
        classes = profile.get("classes", [])
        if not subjects or not classes:
            return "Сначала выберите предметы и классы через «Начать заново»."
        lessons = schedule.lessons_for_teacher(subjects, classes)
        if weekly:
            return format_weekly_schedule("Ваши уроки на неделю", lessons)
        return format_schedule("Ваши уроки", lessons)

    return "Сначала выберите роль через «Начать заново»."


def send_profile_ready(vk, peer_id, profile, schedule):
    role = profile.get("role")
    if role == "teacher":
        hint_text = (
            "Нажмите «Расписание», чтобы получить уроки на сегодня,\n"
            "или «Расписание на неделю», чтобы увидеть все уроки."
        )
    else:
        hint_text = "Нажмите «Расписание», чтобы получить уроки."
    send(
        vk,
        peer_id,
        f"Готово, сохранил профиль.\n\n{profile_text(profile)}\n\n{hint_text}",
        main_keyboard(),
    )


def handle_message(vk, storage, schedule, user_id, peer_id, text):
    text = (text or "").strip()
    user = storage.get_user(user_id)
    text_lower = text.lower()

    if not text or text_lower in ("/start", "start", "начать", "начать заново"):
        storage.reset_user(user_id)
        ask_role(vk, peer_id)
        return

    if text_lower == "мой профиль":
        send(vk, peer_id, profile_text(user.get("profile", {})), main_keyboard())
        return

    if text_lower in ("расписание", "моё расписание", "мое расписание"):
        send_long(vk, peer_id, schedule_text(user.get("profile", {}), schedule), main_keyboard())
        return

    if text_lower in ("расписание на неделю", "недельное расписание", "расписание недели"):
        send_long(vk, peer_id, schedule_text(user.get("profile", {}), schedule, weekly=True), main_keyboard())
        return

    if text_lower == "назад":
        role = user.get("profile", {}).get("role")
        if role in ("student", "parent"):
            user["step"] = "grade"
            storage.update_user(user_id, user)
            ask_grade(vk, peer_id, schedule)
            return

    step = user.get("step", "role")
    profile = user.setdefault("profile", {})

    if step == "role":
        role = parse_role(text)
        if not role:
            ask_role(vk, peer_id)
            return
        profile.clear()
        profile["role"] = role
        if role in ("student", "parent"):
            user["step"] = "grade"
            storage.update_user(user_id, user)
            ask_grade(vk, peer_id, schedule)
        else:
            user["step"] = "teacher_subjects"
            storage.update_user(user_id, user)
            ask_teacher_subjects(vk, peer_id, schedule)
        return

    if step == "grade":
        grade = "".join(ch for ch in text if ch.isdigit())
        if grade not in schedule.grades:
            ask_grade(vk, peer_id, schedule)
            return
        profile["grade"] = grade
        user["step"] = "class_letter"
        storage.update_user(user_id, user)
        send(
            vk,
            peer_id,
            "Выберите букву класса.",
            class_keyboard(schedule.grades[grade]),
        )
        return

    if step == "class_letter":
        grade = profile.get("grade")
        options = schedule.grades.get(grade, [])
        normalized = text_lower.replace(" ", "")
        selected = next((name for name in options if name.lower() == normalized), None)
        if not selected and grade:
            selected = next((name for name in options if name.lower().replace(grade, "") == normalized), None)
        if not selected:
            send(vk, peer_id, "Не нашёл такой класс. Выберите вариант из списка.", class_keyboard(options))
            return
        profile["class_name"] = selected
        user["step"] = "done"
        storage.update_user(user_id, user)
        send_profile_ready(vk, peer_id, profile, schedule)
        return

    if step == "teacher_subjects":
        numbers = parse_numbers(text, len(schedule.subjects))
        if not numbers:
            ask_teacher_subjects(vk, peer_id, schedule)
            return
        profile["subjects"] = [schedule.subjects[number - 1] for number in numbers]
        user["step"] = "teacher_classes"
        storage.update_user(user_id, user)
        ask_teacher_classes(vk, peer_id, schedule)
        return

    if step == "teacher_classes":
        numbers = parse_numbers(text, len(schedule.classes))
        if not numbers:
            ask_teacher_classes(vk, peer_id, schedule)
            return
        profile["classes"] = [schedule.classes[number - 1] for number in numbers]
        user["step"] = "done"
        storage.update_user(user_id, user)
        send_profile_ready(vk, peer_id, profile, schedule)
        return

    send(vk, peer_id, "Нажмите «Расписание», чтобы получить уроки.", main_keyboard())


def get_message(event):
    obj = getattr(event, "obj", None) or getattr(event, "object", None) or {}
    message = obj.get("message", obj) if isinstance(obj, dict) else getattr(obj, "message", obj)
    return message


def run():
    if vk_api is None:
        raise RuntimeError("Не установлен пакет vk_api. Выполните: pip install -r requirements.txt")
    if not VK_TOKEN:
        raise RuntimeError("Не найден VK_TOKEN. Укажите токен в переменной окружения или первой строкой в key.txt.")
    if not VK_GROUP_ID:
        raise RuntimeError("Не найден VK_GROUP_ID. Укажите ID группы в переменной окружения или второй строкой в key.txt.")

    # Определяем источник расписания: Google Таблица или xlsx файл
    schedule = None
    if GOOGLE_SPREADSHEET_ID:
        print(f"Загрузка расписания из Google Таблицы (ID: {GOOGLE_SPREADSHEET_ID})...")
        from config import GOOGLE_CREDENTIALS_FILE
        credentials_path = Path(GOOGLE_CREDENTIALS_FILE) if Path(GOOGLE_CREDENTIALS_FILE).is_absolute() else BASE_DIR / GOOGLE_CREDENTIALS_FILE
        try:
            from schedule_reader import load_schedule_from_google
            schedule = load_schedule_from_google(credentials_path, GOOGLE_SPREADSHEET_ID)
            print("Расписание успешно загружено из Google Таблицы.")
        except Exception as e:
            print(f"Ошибка загрузки из Google Таблицы: {e}")
            print("Попробуем загрузить из локального файла...")
    
    # Если не удалось загрузить из Google или ID не указан, используем локальный файл
    if schedule is None:
        if not SCHEDULE_FILE.exists():
            raise RuntimeError(f"Не найден файл расписания: {SCHEDULE_FILE}")
        print(f"Загрузка расписания из файла: {SCHEDULE_FILE}")
        schedule = load_schedule(SCHEDULE_FILE)
    storage = JsonStorage(USERS_FILE)

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, VK_GROUP_ID)

    print("Bot started")
    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue
        message = get_message(event)
        peer_id = message.get("peer_id")
        user_id = message.get("from_id")
        text = message.get("text", "")
        if peer_id and user_id:
            handle_message(vk, storage, schedule, user_id, peer_id, text)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"Bot stopped: {exc}", file=sys.stderr)
        raise
