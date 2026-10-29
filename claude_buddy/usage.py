"""오늘 Claude Code 사용량: 세션 기록(JSONL)의 usage를 모아 센다 (읽기만, 바깥으로 보내지 않음)."""

import datetime
import json

from .config import PROJECTS

_seen = {}  # 파일 -> (읽은 위치, {메시지 id: (날짜, 세션, 입력, 캐시 읽기, 출력)}) — 메뉴 열 때마다 새 줄만 읽음


def _scan(path):
    off, msgs = _seen.get(path, (0, {}))
    try:
        size = path.stat().st_size
    except OSError:
        return {}
    if size < off:  # 파일이 줄었으면 처음부터
        off, msgs = 0, {}
    if size > off:
        with open(path, "rb") as f:
            f.seek(off)
            data = f.read(size - off)
        cut = data.rfind(b"\n") + 1
        off += cut
        session = path.stem if path.parent.parent == PROJECTS else path.parent.parent.name  # 서브에이전트는 부모 세션
        for line in data[:cut].split(b"\n"):
            if b'"usage"' not in line:
                continue
            try:
                o = json.loads(line)
                m = o["message"]
                u = m["usage"]
                day = datetime.datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).astimezone().date()
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if o.get("type") != "assistant":
                continue
            # 한 답변이 여러 줄로 나뉘어 같은 id로 기록되므로 마지막 줄만 남김
            msgs[m.get("id") or o.get("uuid")] = (day, session, u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0),
                                                  u.get("cache_read_input_tokens", 0), u.get("output_tokens", 0))
        _seen[path] = (off, msgs)
    return msgs


def today():
    """(세션 수, 응답 수, 입력, 캐시 읽기, 출력) 토큰."""
    day = datetime.date.today()
    start = datetime.datetime.combine(day, datetime.time()).timestamp()
    rows = []
    for path in PROJECTS.glob("**/*.jsonl"):
        try:
            if path.stat().st_mtime < start:
                continue
        except OSError:
            continue
        rows += [r for r in _scan(path).values() if r[0] == day]
    return (len({r[1] for r in rows}), len(rows), *(sum(r[i] for r in rows) for i in (2, 3, 4)))


def fmt(n):
    return f"{n / 1e8:.1f}억" if n >= 1e8 else f"{n / 1e4:.1f}만" if n >= 1e4 else f"{n:,}"


if __name__ == "__main__":  # 셀프 체크: python -m claude_buddy.usage
    assert fmt(123) == "123" and fmt(12_300) == "1.2만" and fmt(250_000_000) == "2.5억"
    print(today())
