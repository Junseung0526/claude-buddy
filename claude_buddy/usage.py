"""Claude Code 사용량: 세션 기록(JSONL)의 usage를 날짜·프로젝트별로 모아 센다 (읽기만, 바깥으로 보내지 않음)."""

import datetime
import json
from pathlib import Path

from .config import PROJECTS

_seen = {}  # 파일 -> (읽은 위치, {메시지 id: (날짜, 세션, 프로젝트, 입력, 캐시 읽기, 출력)}) — 메뉴 열 때마다 새 줄만 읽음


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
        main = path.parent.parent == PROJECTS
        session = path.stem if main else path.parent.parent.name  # 서브에이전트는 부모 세션
        project = project_name((path.parent if main else path.parent.parent.parent).name)
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
            msgs[m.get("id") or o.get("uuid")] = (day, session, project, u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0),
                                                  u.get("cache_read_input_tokens", 0), u.get("output_tokens", 0))
        _seen[path] = (off, msgs)
    return msgs


def project_name(folder):
    """세션 폴더 이름(경로의 /를 -로 바꾼 것)을 읽기 좋게: -Users-me-Documents-app -> Documents-app."""
    home = str(Path.home()).replace("/", "-")
    return "~" if folder == home else folder.removeprefix(home + "-")


def rows(days=7):
    """최근 days일의 응답별 기록 [(날짜, 세션, 프로젝트, 입력, 캐시 읽기, 출력)]."""
    first = datetime.date.today() - datetime.timedelta(days=days - 1)
    start = datetime.datetime.combine(first, datetime.time()).timestamp()
    out = []
    for path in PROJECTS.glob("**/*.jsonl"):
        try:
            if path.stat().st_mtime < start:
                continue
        except OSError:
            continue
        out += [r for r in _scan(path).values() if r[0] >= first]
    return out


def today():
    """(세션 수, 응답 수, 입력, 캐시 읽기, 출력) 토큰."""
    day = datetime.date.today()
    rs = [r for r in rows(1) if r[0] == day]
    return (len({r[1] for r in rs}), len(rs), *(sum(r[i] for r in rs) for i in (3, 4, 5)))


def summary(days=7):
    """창에 그릴 값: 오늘 합계, 날짜별 출력 [(날짜, 출력)], 오늘 프로젝트별 출력 [(이름, 출력)] (많은 순)."""
    rs = rows(days)
    day = datetime.date.today()
    per_day = [(day - datetime.timedelta(days=k), 0) for k in range(days - 1, -1, -1)]
    totals = {d: 0 for d, _ in per_day}
    projects = {}
    for r in rs:
        totals[r[0]] = totals.get(r[0], 0) + r[5]
        if r[0] == day:
            projects[r[2]] = projects.get(r[2], 0) + r[5]
    return today(), [(d, totals[d]) for d, _ in per_day], sorted(projects.items(), key=lambda x: -x[1])


def fmt(n):
    return f"{n / 1e8:.1f}억" if n >= 1e8 else f"{n / 1e4:,.0f}만" if n >= 1e7 else f"{n / 1e4:.1f}만" if n >= 1e4 else f"{n:,}"


if __name__ == "__main__":  # 셀프 체크: python -m claude_buddy.usage
    assert fmt(123) == "123" and fmt(12_300) == "1.2만" and fmt(250_000_000) == "2.5억" and fmt(21_300_000) == "2,130만"
    print(today())
    t, by_day, by_project = summary()
    assert len(by_day) == 7 and by_day[-1][0] == datetime.date.today() and by_day[-1][1] == t[4]
    assert project_name(str(Path.home()).replace("/", "-") + "-Documents-app") == "Documents-app"
    print(by_day, by_project[:3])
