"""Claude Code 세션 기록(JSONL)을 읽어 메인·서브에이전트의 현재 작업 라벨을 만든다."""

import datetime
import json
import time
from pathlib import Path

from .config import PROJECTS


DONE_LABEL = "작업 완료"


def tool_label(name, inp):
    base = lambda p: Path(str(p)).name or str(p)
    if name == "Read":
        return f"읽는 중 · {base(inp.get('file_path', ''))}"
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return f"수정 중 · {base(inp.get('file_path') or inp.get('notebook_path', ''))}"
    if name == "Bash":
        return "실행 중 · " + (inp.get("description") or inp.get("command", ""))[:30]
    if name in ("Grep", "Glob"):
        return "코드 검색 중"
    if name in ("WebFetch", "WebSearch"):
        return "웹 검색 중"
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


class Tail:
    """JSONL 파일의 새 줄만 읽어서 마지막 작업 라벨을 추적."""

    def __init__(self, path, backlog=200_000):
        self.path = path
        self.off = max(0, path.stat().st_size - backlog)
        self.skip_partial = self.off > 0
        self.label, self.pending, self.last = None, set(), 0.0

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
                    self.feed(json.loads(line))
                except ValueError:
                    pass

    def feed(self, o):
        t, msg = o.get("type"), o.get("message") or {}
        try:
            ts = datetime.datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError, AttributeError):
            ts = time.time()
        content = msg.get("content")
        if t == "user":
            if isinstance(content, str):
                self.label, self.last = "새 요청 받음", ts
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_result":
                        self.pending.discard(b.get("tool_use_id"))
                        self.label, self.last = "생각 중", ts
        elif t == "assistant" and isinstance(content, list):
            for b in content:
                bt = b.get("type")
                if bt == "tool_use":
                    self.pending.add(b.get("id"))
                    self.label = tool_label(b.get("name", ""), b.get("input") or {})
                elif bt == "thinking":
                    self.label = "생각 중"
                elif bt == "text":
                    self.label = "답변 작성 중"
            self.last = ts

    def busy(self, now):
        # 도구 결과를 기다리는 중이면 오래 걸려도 일하는 중
        return bool(self.pending) and now - self.last < 600 or now - self.last < 25


class Activity:
    def __init__(self):
        self.main = None
        self.subs = {}  # agent id -> {"tail", "desc", "finished", "meta_mtime"}
        self.done_label_until = 0.0

    def poll(self, now):
        try:
            files = [(p.stat().st_mtime, p) for p in PROJECTS.glob("*/*.jsonl")]
        except OSError:
            files = []
        files = [f for f in files if now - f[0] < 900]
        if not files:
            self.main = None
            return
        newest = max(files)[1]
        if not self.main or self.main.path != newest:
            self.main, self.subs = Tail(newest), {}
        was_busy = self.main.busy(now)
        self.main.poll()
        if was_busy and not self.main.busy(now):
            self.done_label_until = now + 8
        sub_dir = newest.with_suffix("") / "subagents"
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

    def busy(self, now):
        return bool(self.main) and self.main.busy(now)

    def label(self, now):
        if not self.main:
            return None
        if self.main.busy(now):
            return self.main.label or "생각 중"
        return DONE_LABEL if now < self.done_label_until else None

    def active_subs(self):
        return {aid: s for aid, s in self.subs.items() if s["tail"]}
