import random
import sys

from bot_core import KEYBOARD_CLASS, KEYBOARD_GRADE, KEYBOARD_MAIN, KEYBOARD_ROLE, handle_message
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


def role_keyboard(_options):
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


def main_keyboard(_options):
    return make_keyboard(
        [
            [("Расписание", VkKeyboardColor.POSITIVE), ("Мой профиль", VkKeyboardColor.PRIMARY)],
            [("Начать заново", VkKeyboardColor.NEGATIVE)],
        ]
    )


KEYBOARD_BUILDERS = {
    KEYBOARD_ROLE: role_keyboard,
    KEYBOARD_GRADE: grade_keyboard,
    KEYBOARD_CLASS: class_keyboard,
    KEYBOARD_MAIN: main_keyboard,
}


def build_keyboard(reply):
    if not reply.keyboard:
        return None
    builder = KEYBOARD_BUILDERS.get(reply.keyboard)
    if builder is None:
        return None
    return builder(reply.keyboard_options)


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


def send_reply(vk, peer_id, reply):
    send_long(vk, peer_id, reply.text, build_keyboard(reply))


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
    if not SCHEDULE_FILE.exists():
        raise RuntimeError(f"Не найден файл расписания: {SCHEDULE_FILE}")

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
            reply = handle_message(storage, schedule, user_id, text)
            send_reply(vk, peer_id, reply)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"Bot stopped: {exc}", file=sys.stderr)
        raise
