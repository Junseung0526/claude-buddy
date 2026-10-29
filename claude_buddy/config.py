"""경로·기본 설정·물리 상수와 설정 저장. 선택 모듈 aws_tips도 여기서 한 번만 불러온다."""

import json
import os
from pathlib import Path

try:  # AWS 시험 팁 (선택 기능): aws_tips.py를 지우면 순수 펫
    from . import aws_tips
except ImportError:
    aws_tips = None


DATA_DIR = Path.home() / "Library" / "Application Support" / "Claude Buddy"  # 앱 번들 안은 쓰기 불가
SETTINGS_FILE = DATA_DIR / "settings.json"
PROJECTS = Path(os.environ.get("BUDDY_PROJECTS", Path.home() / ".claude" / "projects"))
DEFAULTS = {"interval": 300, "scale": 6, "speed": 55, "sound": True, "windows": True, "activity": True}
SHOW_SEC = 25
GRAVITY = 2200.0
BUBBLE_W = 380
MAX_MINIS = 6


def load_settings():
    try:
        cfg = {**DEFAULTS, **json.loads(SETTINGS_FILE.read_text())}
        cfg["interval"] = max(60, cfg["interval"])  # 예전 테스트 값(1초 등) 방지
        return cfg
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(cfg):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
