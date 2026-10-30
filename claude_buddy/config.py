"""경로·기본 설정·물리 상수와 설정 저장."""

import json
import os
from pathlib import Path


DATA_DIR = Path.home() / "Library" / "Application Support" / "Claude Buddy"  # 앱 번들 안은 쓰기 불가
SETTINGS_FILE = DATA_DIR / "settings.json"
PROJECTS = Path(os.environ.get("BUDDY_PROJECTS", Path.home() / ".claude" / "projects"))
CODEX_SESSIONS = Path(os.environ.get("BUDDY_CODEX", Path.home() / ".codex" / "sessions"))
# Antigravity CLI·IDE 로그 폴더
AGY_LOGS = [Path(p) for p in os.environ.get("BUDDY_AGY", "").split(":") if p] or [
    Path.home() / ".gemini" / "antigravity-cli" / "log", Path.home() / ".gemini" / "antigravity" / "log"]
RELEASES = "https://github.com/Junseung0526/claude-buddy/releases/latest"
RELEASES_API = "https://api.github.com/repos/Junseung0526/claude-buddy/releases/latest"

DEFAULTS = {"scale": 6, "speed": 55, "sound": True, "windows": True, "activity": True, "notify": True, "updates": True, "color": "#D97757", "hat": "none", "glasses": False, "lang": "auto", "ask_provider": "claude"}
SHOW_SEC = 25
GRAVITY = 2200.0
BUBBLE_W = 380
MAX_MINIS = 6


def load_settings():
    try:
        # 언어 설정이 생기기 전부터 쓰던 사람은 한국어로 쓰고 있었으므로 그대로 한국어
        return {**DEFAULTS, "lang": "ko", **json.loads(SETTINGS_FILE.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(cfg):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
