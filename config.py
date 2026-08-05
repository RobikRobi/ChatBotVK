import os
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
KEY_FILE = BASE_DIR / ".env"
SCHEDULE_FILE = BASE_DIR / "outputs" / "soo_pdf_conversion" / "soo_schedule.xlsx"
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"


def _read_key_file():
    if not KEY_FILE.exists():
        return {}

    values = {}
    plain_lines = []
    for raw_line in KEY_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip()
        else:
            plain_lines.append(line)

    if plain_lines:
        values.setdefault("VK_TOKEN", plain_lines[0])
    if len(plain_lines) > 1:
        values.setdefault("VK_GROUP_ID", plain_lines[1])
    return values


_file_values = _read_key_file()

VK_TOKEN = os.getenv("VK_TOKEN") or _file_values.get("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID") or _file_values.get("VK_GROUP_ID")

if VK_GROUP_ID:
    group_id_text = str(VK_GROUP_ID).strip()
    group_id_match = re.search(r"(?:club|public)?(\d+)", group_id_text)
    if not group_id_match:
        raise RuntimeError("VK_GROUP_ID должен быть числом или ссылкой вида https://vk.ru/club123456.")
    VK_GROUP_ID = int(group_id_match.group(1))
