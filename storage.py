import json
from pathlib import Path


class JsonStorage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save(self):
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def get_user(self, user_id: int):
        return self._data.setdefault(str(user_id), {"step": "role", "profile": {}})

    def update_user(self, user_id: int, user_data):
        self._data[str(user_id)] = user_data
        self.save()

    def reset_user(self, user_id: int):
        self._data[str(user_id)] = {"step": "role", "profile": {}}
        self.save()
        return self._data[str(user_id)]
