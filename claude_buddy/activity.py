"""에이전트 작업 기록을 읽어 현재 작업 라벨을 만든다.

Claude Code(메인·서브에이전트) 세션 JSONL, Codex(GPT) 세션 JSONL, Antigravity(Gemini) 로그를 따라간다."""

import datetime
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from .config import AGY_LOGS, CODEX_SESSIONS, PROJECTS


DONE_LABEL = "작업 완료"
ASK_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
QUICK_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "WebFetch"}
QUIET_SEC = 900  # 이보다 오래 안 바뀐 기록 파일은 무시


def stamp(o):
    try:
        return datetime.datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, AttributeError):
        return time.time()


def newest(paths, now):
    files = []
    for p in paths:
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            pass
    files = [f for f in files if now - f[0] < QUIET_SEC]
    return max(files)[1] if files else None


def tool_label(name, inp):
    base = lambda p: Path(str(p)).name or str(p)
    if name == "Read":
        at = f" ({inp['offset']}줄부터)" if inp.get("offset") else ""
        return f"읽는 중 · {base(inp.get('file_path', ''))}{at}"
    if name == "Write":
        return f"작성 중 · {base(inp.get('file_path', ''))}"
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        return f"수정 중 · {base(inp.get('file_path') or inp.get('notebook_path', ''))}"
    if name == "Bash":
        return "실행 중 · " + (inp.get("description") or inp.get("command", ""))[:30]
    if name == "Grep":
        return f"코드 검색 · '{str(inp.get('pattern', ''))[:20]}'"
    if name == "Glob":
        return f"파일 찾는 중 · {str(inp.get('pattern', ''))[:24]}"
    if name == "WebSearch":
        return f"웹 검색 · {str(inp.get('query', ''))[:24]}"
    if name == "WebFetch":
        return "웹 읽는 중 · " + (urlparse(str(inp.get("url", ""))).netloc or "페이지")
    if name in ("Agent", "Task"):
        return "서브에이전트 · " + (inp.get("description") or "호출")[:30]
    if name == "Skill":
        return f"스킬 · {inp.get('skill', '')}"
    if name in ("TodoWrite",) or name.endswith("update_plan"):
        return "계획 정리 중"
    if name == "Workflow":
        return "워크플로 실행 중"
    if name.startswith("mcp__"):
        return "도구 · " + name.split("__")[-1][:24]
    return f"도구 · {name}"


# 라벨 앞부분 -> 애니메이션 종류 (Claude·Codex·Antigravity 라벨 공용)
KINDS = (("읽는", "read"), ("작성 중", "edit"), ("수정 중", "edit"), ("파일 수정", "edit"), ("실행 중", "run"),
         ("명령 실행", "run"), ("워크플로", "run"), ("도구", "run"), ("코드 검색", "search"), ("파일 찾는", "search"),
         ("검색 중", "search"), ("웹", "web"), ("계획", "plan"), ("답변 작성", "answer"), ("서브에이전트", "agent"))


def label_kind(label):
    """작업 라벨로 어떤 동작을 보여줄지 정함. 모르는 건 생각 중."""
    return next((k for prefix, k in KINDS if (label or "").startswith(prefix)), "think")


def elapsed(sec):
    """오래 걸리는 단계만 경과 시간 표시. 칩 창을 덜 새로 만들도록 5초 단위."""
    if sec < 10:
        return ""
    return f" · {int(sec) // 5 * 5}초" if sec < 60 else f" · {int(sec) // 60}분"


class Tail:
    """JSONL 파일의 새 줄만 읽어서 마지막 작업 라벨을 추적."""

    def __init__(self, path, backlog=200_000):
        self.path = path
        self.off = max(0, path.stat().st_size - backlog)
        self.skip_partial = self.off > 0
        self.label, self.pending, self.last = None, {}, 0.0  # pending: 결과를 기다리는 도구 id -> 이름
        self.ended = False  # 답변을 마쳤다는 기록(end_turn)을 봤는지
        self.since = time.time()  # 지금 라벨이 붙은 시각

    @property
    def label(self):
        return getattr(self, "_label", None)

    @label.setter
    def label(self, text):
        if text != getattr(self, "_label", None):
            self._label, self.since = text, time.time()

    def text(self, now):
        """칩에 띄울 글자: 라벨 + 오래 걸리면 경과 시간."""
        return (self.label or "준비 중") + (elapsed(now - self.since) if self.busy(now) else "")

    def poll(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self.off:  # 파일이 줄었으면 처음부터
            self.off, self.skip_partial = 0, False
        if size == self.off:
            return
        with open(self.path, "rb") as f:
            f.seek(self.off)
            data = f.read(size - self.off)
        cut = data.rfind(b"\n") + 1  # 덜 쓰인 마지막 줄은 다음 번에
        self.off += cut
        lines = data[:cut].split(b"\n")
        if self.skip_partial:
            lines, self.skip_partial = lines[1:], False
        for line in lines:
            if line.strip():
                try:
                    self.feed_line(line)
                except ValueError:
                    pass

    def feed_line(self, line):
        self.feed(json.loads(line))

    def feed(self, o):
        t, msg, ts = o.get("type"), o.get("message") or {}, stamp(o)
        content = msg.get("content")
        if t in ("user", "assistant"):
            self.ended = False
        if t == "user":
            if isinstance(content, str):
                self.label, self.last = "새 요청 받음", ts
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_result":
                        self.pending.pop(b.get("tool_use_id"), None)
                        self.label, self.last = "생각 중", ts
        elif t == "assistant" and isinstance(content, list):
            for b in content:
                bt = b.get("type")
                if bt == "tool_use":
                    self.pending[b.get("id")] = b.get("name", "")
                    self.label = tool_label(b.get("name", ""), b.get("input") or {})
                elif bt == "thinking":
                    self.label = "생각 중"
                elif bt == "text":
                    self.label = "답변 작성 중"
            self.last = ts
            # 턴이 끝나면 25초 기다리지 않고 바로 완료 (Stop 훅이 이어가면 다음 기록이 다시 작업 중으로 바꿈)
            self.ended = msg.get("stop_reason") == "end_turn" and not self.pending

    def busy(self, now):
        if self.ended:
            return False
        # 도구 결과를 기다리는 중이면 오래 걸려도 일하는 중
        return bool(self.pending) and now - self.last < 600 or now - self.last < 25

    def waiting(self, now):
        """내 대답이나 권한 허락을 기다리는 중이면 그 이유. 기록에 직접 남지 않아 도구 종류와 대기 시간으로 짐작."""
        if self.ended or now - self.last > 600:
            return None
        names = set(self.pending.values())
        if names & ASK_TOOLS:
            return "질문에 답해 주세요"
        if names & QUICK_TOOLS and now - self.last > 8:  # 허락만 받으면 바로 끝나는 도구가 오래 걸리면 권한 대기
            return "권한 확인"
        return None


def codex_label(name):
    if name in ("exec", "shell", "local_shell", "exec_command"):
        return "명령 실행 중"
    if name == "apply_patch":
        return "파일 수정 중"
    if "search" in name:
        return "검색 중"
    return f"도구 · {name}"


class CodexTail(Tail):
    """Codex(GPT) 세션 rollout JSONL: task_started ~ task_complete가 한 턴."""

    def feed(self, o):
        p, ts, t = o.get("payload") or {}, stamp(o), o.get("type")
        kind = p.get("type") or ""
        if t == "event_msg":
            if kind == "task_started":
                self.label, self.ended, self.last = "새 요청 받음", False, ts
            elif kind == "task_complete":
                self.pending.clear()
                self.ended, self.last = True, ts
            return
        if t != "response_item":
            return
        if kind in ("function_call", "custom_tool_call", "local_shell_call"):
            self.pending[p.get("call_id")] = p.get("name") or "shell"
            self.label = codex_label(p.get("name") or "shell")
        elif kind.endswith("_call_output"):
            self.pending.pop(p.get("call_id"), None)
            self.label = "생각 중"
        elif kind == "reasoning":
            self.label = "생각 중"
        elif kind == "message" and p.get("role") == "assistant":
            self.label = "답변 작성 중"
        else:
            return
        self.last = ts


AGY_LINE = re.compile(rb"^[IWE](\d{4}) (\d{2}:\d{2}:\d{2})")


class AgyTail(Tail):
    """Antigravity 서버 로그: 사용자 메시지 전달 ~ Stream completed가 한 턴."""

    def feed_line(self, line):
        m = AGY_LINE.match(line)
        if not m:
            return
        # shortcut: 로그 시각에 연도가 없어 올해로 가정, 연말연시 자정 무렵 한 턴은 어긋날 수 있음
        ts = datetime.datetime.strptime(f"{datetime.date.today().year}{m[1].decode()} {m[2].decode()}", "%Y%m%d %H:%M:%S").timestamp()
        if b"user message to conversation" in line:
            self.label, self.ended, self.last = "새 요청 받음", False, ts
        elif b"Tool confirmation for conversation" in line:
            step = re.search(rb"step (\d+)", line)
            self.label, self.last = f"도구 실행 중 · {step[1].decode()}단계" if step else "도구 실행 중", ts
        elif b"Stream completed for" in line:
            self.ended, self.last = True, ts

    def busy(self, now):
        # 로그는 생각하는 동안 조용하므로 완료 줄이 나올 때까지(최대 10분) 작업 중으로 봄
        return self.last > 0 and not self.ended and now - self.last < 600


# (키, 이름, 캐릭터 종류, 기록 파일 찾기, 추적기)
OTHER_AGENTS = (
    ("codex", "Codex (GPT)", "gpt", lambda: CODEX_SESSIONS.glob("*/*/*/rollout-*.jsonl"), CodexTail),
    ("antigravity", "Antigravity (Gemini)", "gemini", lambda: [p for d in AGY_LOGS for p in d.glob("cli-*.log")], AgyTail),
)


class Activity:
    def __init__(self):
        self.main = None
        self.subs = {}  # agent id -> {"tail", "desc", "finished", "meta_mtime"}
        self.others = {}  # "codex"·"antigravity" -> {"tail", "desc", "kind", "finished"}
        self.done_label_until = 0.0
        self.busy_since, self.finished_after = time.time(), 0.0  # 끝난 작업이 걸린 시간 (앱이 읽고 0으로)

    def poll(self, now):
        self.poll_others(now)
        path = newest(PROJECTS.glob("*/*.jsonl"), now)
        if not path:
            self.main = None
            return
        if not self.main or self.main.path != path:
            self.main, self.subs = Tail(path), {}
        was_busy = self.main.busy(now)
        self.main.poll()
        is_busy = self.main.busy(now)
        if is_busy and not was_busy:
            self.busy_since = now
        if was_busy and not is_busy:
            self.done_label_until = now + 8
            self.finished_after = now - self.busy_since
        sub_dir = path.with_suffix("") / "subagents"
        for meta in sub_dir.glob("*.meta.json") if sub_dir.is_dir() else []:
            aid = meta.name.split(".")[0]
            try:
                mt = meta.stat().st_mtime
                s = self.subs.get(aid)
                if s and s["meta_mtime"] == mt:
                    continue
                info = json.loads(meta.read_text())
            except (OSError, ValueError):
                continue
            log = meta.with_name(aid + ".jsonl")
            if s is None:
                if info.get("finished") or not log.exists() or now - log.stat().st_mtime > 600:
                    self.subs[aid] = {"tail": None, "desc": "", "finished": True, "meta_mtime": mt, "seen_done": True}
                    continue
                s = self.subs[aid] = {"tail": Tail(log, backlog=50_000), "seen_done": False}
            s.update(desc=info.get("description", "서브에이전트"), finished=bool(info.get("finished")), meta_mtime=mt)
        for s in self.subs.values():
            if s["tail"] and not s["finished"]:
                s["tail"].poll()
                try:
                    quiet = now - s["tail"].path.stat().st_mtime > 600
                except OSError:
                    quiet = True
                if quiet:
                    s["finished"] = True  # 오래 조용하거나 사라지면 끝난 걸로

    def poll_others(self, now):
        for key, name, kind, find, cls in OTHER_AGENTS:
            path = newest(find(), now)
            o = self.others.get(key)
            if not path:
                if o:
                    o["finished"] = True
                continue
            if not o or o["tail"].path != path:
                o = self.others[key] = {"tail": cls(path), "desc": name, "kind": kind, "finished": True}
            o["tail"].poll()
            o["finished"] = not o["tail"].busy(now)

    def sub(self, aid):
        return self.subs.get(aid) or self.others.get(aid)

    def busy(self, now):
        return bool(self.main) and self.main.busy(now)

    def waiting(self, now):
        return self.main.waiting(now) if self.main else None

    def label(self, now):
        if not self.main:
            return None
        if self.waiting(now):
            return f"확인 필요 · {self.waiting(now)}"
        if self.main.busy(now):
            return self.main.text(now) if self.main.label else "생각 중"
        return DONE_LABEL if now < self.done_label_until else None

    def active_subs(self):
        """작은 캐릭터로 보여줄 대상: Claude 서브에이전트 + 다른 에이전트."""
        return {**{aid: s for aid, s in self.subs.items() if s["tail"]}, **self.others}
