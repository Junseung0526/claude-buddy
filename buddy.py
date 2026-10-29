#!/usr/bin/env python3
"""화면을 돌아다니며 Claude Code 작업 상황을 보여주는 Claude 캐릭터 데스크톱 펫 (macOS).
aws_tips.py가 있으면 AWS 시험 팁·물어보기 기능이 켜지고, 지우면 순수 펫으로 동작함.

설치·실행: ./make_app.sh 한 번 → "Claude 버디.app" 더블클릭
직접 실행: .venv/bin/python buddy.py

상호작용
  클릭 다음 팁 · 더블클릭 쓰다듬기 · 드래그 들기/던지기 · 커서 올리기 손 흔들기
  우클릭(또는 메뉴바 ✳︎) 물어보기 / 간식 / 공놀이 / 따라오기 / 집중 타이머 / 재우기 / 설정
  Claude Code가 일하면 머리 위에 지금 하는 작업이 뜨고, 서브에이전트마다 작은 캐릭터가 나와서 같이 일함
"""
import argparse
import datetime
import json
import math
import os
import random
import threading
import time
from pathlib import Path

import objc
from AppKit import (
    NSAffineTransform, NSApp, NSAppearance, NSAppearanceNameAqua, NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
    NSBezierPath, NSBitmapImageFileTypePNG, NSBitmapImageRep, NSColor, NSEvent, NSFont, NSFontAttributeName,
    NSForegroundColorAttributeName, NSImage, NSMakeRect, NSMenu, NSMenuItem, NSScreen, NSSound, NSStatusBar,
    NSStatusWindowLevel, NSString, NSTextField, NSView, NSWindow, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowCollectionBehaviorStationary, NSWindowStyleMaskBorderless,
    NSWorkspace,
)
from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer
from PyObjCTools import AppHelper
from Quartz import (
    CGEventSourceSecondsSinceLastEventType, CGWindowListCopyWindowInfo, kCGAnyInputEventType,
    kCGEventSourceStateHIDSystemState, kCGNullWindowID, kCGWindowListExcludeDesktopElements,
    kCGWindowListOptionOnScreenOnly,
)

try:  # AWS 시험 팁 (선택 기능): aws_tips.py를 지우면 순수 펫
    import aws_tips
except ImportError:
    aws_tips = None

HERE = Path(__file__).resolve().parent
SETTINGS_FILE = HERE / "settings.json"
PROJECTS = Path(os.environ.get("BUDDY_PROJECTS", Path.home() / ".claude" / "projects"))
DEFAULTS = {"interval": 60, "scale": 6, "speed": 55, "sound": True, "windows": True, "activity": True}
SHOW_SEC = 25
GRAVITY = 2200.0
BUBBLE_W = 380
MAX_MINIS = 6


# ---------------------------------------------------------------- 데이터·설정
def load_settings():
    try:
        return {**DEFAULTS, **json.loads(SETTINGS_FILE.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(cfg):
    SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- Claude Code 작업 감시
def tool_label(name, inp):
    base = lambda p: Path(str(p)).name or str(p)
    if name == "Read":
        return f"📖 {base(inp.get('file_path', ''))} 읽는 중"
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return f"✏️ {base(inp.get('file_path') or inp.get('notebook_path', ''))} 수정 중"
    if name == "Bash":
        return "💻 " + (inp.get("description") or inp.get("command", ""))[:30]
    if name in ("Grep", "Glob"):
        return "🔍 코드 찾는 중"
    if name in ("WebFetch", "WebSearch"):
        return "🌐 웹 검색 중"
    if name in ("Agent", "Task"):
        return "👥 " + (inp.get("description") or "서브에이전트 호출")[:30]
    if name == "Skill":
        return f"📚 {inp.get('skill', '')} 스킬"
    if name in ("TodoWrite",) or name.endswith("update_plan"):
        return "📋 계획 정리 중"
    if name == "Workflow":
        return "🧩 워크플로 실행"
    if name.startswith("mcp__"):
        return "🔌 " + name.split("__")[-1][:24]
    return f"🔧 {name}"


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
                self.label, self.last = "📝 새 요청 받음", ts
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_result":
                        self.pending.discard(b.get("tool_use_id"))
                        self.label, self.last = "💭 생각 중", ts
        elif t == "assistant" and isinstance(content, list):
            for b in content:
                bt = b.get("type")
                if bt == "tool_use":
                    self.pending.add(b.get("id"))
                    self.label = tool_label(b.get("name", ""), b.get("input") or {})
                elif bt == "thinking":
                    self.label = "💭 생각 중"
                elif bt == "text":
                    self.label = "💬 답변 쓰는 중"
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
            return self.main.label or "💭 생각 중"
        return "✅ 작업 완료!" if now < self.done_label_until else None

    def active_subs(self):
        return {aid: s for aid, s in self.subs.items() if s["tail"]}


# ---------------------------------------------------------------- 화면·발판
class World:
    def __init__(self, cfg):
        self.cfg = cfg
        self.plats, self.next_refresh = [], 0.0
        self.refresh(0)

    def refresh(self, now):
        if now < self.next_refresh:
            return
        self.next_refresh = now + 0.4
        screens = NSScreen.screens()
        self.primary_h = screens[0].frame().size.height
        self.vfs = [s.visibleFrame() for s in screens]
        self.frames = [s.frame() for s in screens]
        plats = [(v.origin.x, v.origin.x + v.size.width, v.origin.y, "floor") for v in self.vfs]
        self.windows = []  # 전체화면 감지에도 씀
        infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                                           kCGNullWindowID) or []
        me = os.getpid()
        front = []  # 앞에 있는 창들 (가려진 윗변 계산용)
        for w in infos:
            if w.get("kCGWindowLayer") != 0 or w.get("kCGWindowOwnerPID") == me or w.get("kCGWindowAlpha", 1) == 0:
                continue
            b = w["kCGWindowBounds"]
            x0, w_, h_ = b["X"], b["Width"], b["Height"]
            top = self.primary_h - b["Y"]
            bottom = top - h_
            self.windows.append((w.get("kCGWindowOwnerPID"), x0, b["Y"], w_, h_))
            if w_ >= 150 and h_ >= 80 and self.cfg["windows"]:
                segs = [(x0, x0 + w_)]
                for fx0, fx1, ftop, fbot in front:
                    if fbot - 2 <= top <= ftop + 2:
                        segs = [s for a, b2 in segs for s in ((a, min(b2, fx0)), (max(a, fx1), b2)) if s[1] - s[0] > 1]
                vtop = max((v.origin.y + v.size.height for v in self.vfs if v.origin.x <= x0 + w_ / 2 <= v.origin.x + v.size.width), default=1e9)
                if top < vtop - 40:  # 메뉴바에 붙은 최대화 창은 제외
                    plats += [(a, b2, top, "window") for a, b2 in segs if b2 - a >= 60]
            front.append((x0, x0 + w_, top, bottom))
        self.plats = plats

    def ground(self, cx, max_top):
        tops = [p[2] for p in self.plats if p[0] <= cx <= p[1] and p[2] <= max_top + 0.01]
        return max(tops) if tops else self.floor(cx)

    def xbounds(self, w):
        return min(f.origin.x for f in self.frames), max(f.origin.x + f.size.width for f in self.frames) - w

    def screen_at(self, x, y):
        for v in self.vfs:
            if v.origin.x <= x <= v.origin.x + v.size.width and v.origin.y - 5 <= y <= v.origin.y + v.size.height:
                return v
        return min(self.vfs, key=lambda v: abs(v.origin.x + v.size.width / 2 - x))

    def column(self, cx):
        """x 위치의 화면 (화면 사이 틈이면 가장 가까운 화면)."""
        return min(self.vfs, key=lambda v: 0 if v.origin.x <= cx <= v.origin.x + v.size.width
                   else min(abs(cx - v.origin.x), abs(cx - v.origin.x - v.size.width)))

    def floor(self, cx):
        return self.column(cx).origin.y

    def ceiling(self, cx):
        v = self.column(cx)
        return v.origin.y + v.size.height

    def platform_above(self, cx, y, reach=320, span=280):
        cands = [p for p in self.plats if p[3] == "window" and 30 < p[2] - y < reach
                 and p[1] - p[0] > 80 and abs((p[0] + p[1]) / 2 - cx) < span + (p[1] - p[0]) / 2]
        return random.choice(cands) if cands else None

    def fullscreen_front(self):
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        pid = app.processIdentifier() if app else None
        sizes = {(round(f.size.width), round(f.size.height)) for f in self.frames}
        return any(p == pid and (round(w), round(h)) in sizes and y <= 0 for p, x, y, w, h in self.windows)


# ---------------------------------------------------------------- 그리기 도구
def rgb(h, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(int(h[1:3], 16) / 255, int(h[3:5], 16) / 255, int(h[5:7], 16) / 255, a)


def tone(h, k):
    c = [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    c = [min(255, int(v * k)) if k < 1 else min(255, int(v + (255 - v) * (k - 1))) for v in c]
    return "#%02X%02X%02X" % tuple(c)


ORANGE_HEX = "#D97757"
ORANGE, EYE, PINK, TEAR, GRAY = rgb(ORANGE_HEX), rgb("#1F1F1F"), rgb("#F2A0A8", 0.8), rgb("#7EC8F2"), rgb("#8A8A8A")
MINI_COLORS = ["#E39A5B", "#C96B4E", "#E0866F", "#D98E4A", "#CF7A63", "#E5A177"]


def fill(x, y, w, h, color):
    color.setFill()
    NSBezierPath.fillRect_(NSMakeRect(x, y, w, h))


def floating_window(rect, cls=NSWindow):
    """테두리·배경 없이 모든 앱/스페이스 위에 뜨는 창."""
    w = cls.alloc().initWithContentRect_styleMask_backing_defer_(rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
    w.setOpaque_(False)
    w.setBackgroundColor_(NSColor.clearColor())
    w.setHasShadow_(False)
    w.setLevel_(NSStatusWindowLevel)
    w.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
                             | NSWindowCollectionBehaviorFullScreenAuxiliary)
    w.setReleasedWhenClosed_(False)
    return w


class KeyWindow(NSWindow):
    """글자 입력을 받을 수 있는 테두리 없는 창."""

    def canBecomeKeyWindow(self):
        return True

    def cancelOperation_(self, s):  # Esc
        self.orderOut_(None)


def label(text, size, color, bold=False, width=None):
    f = NSTextField.wrappingLabelWithString_(text) if width else NSTextField.labelWithString_(text)
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    f.setTextColor_(color)
    f.setSelectable_(False)
    if width:
        f.setPreferredMaxLayoutWidth_(width)
    return f


def play(cfg, name):
    if cfg["sound"]:
        s = NSSound.soundNamed_(name)
        if s:
            s.setVolume_(0.25)
            s.play()


# ---------------------------------------------------------------- 캐릭터
class CharView(NSView):
    def initWithCritter_(self, c):
        self = objc.super(CharView, self).initWithFrame_(NSMakeRect(0, 0, c.W, c.H))
        self.c = c
        return self

    def acceptsFirstMouse_(self, e):
        return True

    def mouseDown_(self, e):
        self.c.owner.press(self.c, NSEvent.mouseLocation(), e.clickCount())

    def mouseDragged_(self, e):
        self.c.owner.drag(self.c, NSEvent.mouseLocation())

    def mouseUp_(self, e):
        self.c.owner.release(self.c)

    def rightMouseDown_(self, e):
        NSMenu.popUpContextMenu_withEvent_forView_(self.c.owner.build_menu(NSMenu.alloc().init()), e, self)

    def drawRect_(self, r):
        draw_critter(self.c, self.c.pose())


def draw_critter(c, s):
    P, W = c.P, c.W
    body, hi, lo = c.cols
    base = P * 0.7
    if s["shadow"]:
        rgb("#000000", 0.16).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(W / 2 - 4.5 * P, 0, 9 * P, P * 0.9)).fill()
    tf = NSAffineTransform.transform()  # 발끝 중심으로 기울이기
    tf.translateXBy_yBy_(W / 2, base)
    tf.rotateByDegrees_(s["tilt"])
    tf.translateXBy_yBy_(-W / 2, -base)
    tf.concat()
    by = base + 2 * P + s["bob"]
    bh = 4 * P * s["squash"]
    bw = 8 * P * (2 - s["squash"])
    bx = W / 2 - bw / 2
    k = bw / (8 * P)
    for i, cx in enumerate((0, 2, 5, 7)):  # 다리: 윗끝이 몸통 속까지 이어져 틈이 안 생김
        lift = s["legA"] if i % 2 == 0 else s["legB"]
        fill(bx + cx * P * k, base + lift, P, by + P * 0.5 - base - lift, lo if i in (1, 3) else body)
    fill(bx, by, bw, bh, body)
    fill(bx, by, bw, P * 0.5, lo)  # 아래 그늘
    fill(bx + P * 0.8, by + bh - P * 0.7, P * 1.6, P * 0.35, hi)  # 반짝이
    ay = by + bh * 0.25
    fill(bx - 2 * P, ay + s["armL"], 2 * P, P, body)
    fill(bx + bw, ay + s["armR"], 2 * P, P, body)
    face, ey = s["face"], by + bh * 0.55 + s["lookY"]
    for n, cx in enumerate((3, 8)):
        ex = bx + (cx - 2) * P * k + s["lookX"]
        if face == "happy":
            fill(ex, ey + P * 0.6, P, P * 0.35, EYE)
            fill(ex - P * 0.35, ey + P * 0.25, P * 0.4, P * 0.35, EYE)
            fill(ex + P * 0.95, ey + P * 0.25, P * 0.4, P * 0.35, EYE)
            fill(ex - P * 0.3, ey - P * 0.55, P * 1.6, P * 0.45, PINK)  # 볼
        elif face == "surprised":
            fill(ex - P * 0.15, ey - P * 0.05, P * 1.3, P * 1.4, EYE)
        elif face == "sad":
            fill(ex, ey - P * 0.2, P, P * 1.0, EYE)
            if n == 1:
                fill(ex + P * 0.25, ey - P * 1.1, P * 0.5, P * 0.8, TEAR)
        elif face in ("sleep", "blink"):
            fill(ex, ey + P * 0.45, P, P * 0.25, EYE)
        elif face in ("work", "focus"):
            fill(ex, ey + P * 0.1, P, P * 0.6, EYE)
        elif face == "sleepy":
            fill(ex, ey + P * 0.3, P, P * 0.55, EYE)
        else:
            fill(ex, ey, P, P * 1.25, EYE)
    if face == "surprised":
        fill(bx + bw / 2 - P * 0.35, by + bh * 0.2, P * 0.7, P * 0.7, EYE)
    if s["emote"]:
        text, color = s["emote"]
        attrs = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(max(10, 2.5 * P)), NSForegroundColorAttributeName: color}
        ns = NSString.stringWithString_(text)
        size = ns.sizeWithAttributes_(attrs)
        ns.drawAtPoint_withAttributes_((min(bx + bw + P * 0.5 - size.width / 2, W - size.width), by + bh + P * 0.4 + s["emoteRise"]), attrs)


class Critter:
    """메인·미니 캐릭터 공통: 물리, 걷기, 포즈."""

    def __init__(self, owner, world, scale, x, color, mini=False):
        self.owner, self.world, self.mini = owner, world, mini
        self.color = color
        self.cols = (rgb(color), rgb(tone(color, 1.25)), rgb(tone(color, 0.82)))
        self.P, self.W, self.H = scale, 16 * scale, 13 * scale
        self.x = x
        self.y = world.floor(x + self.W / 2)
        self.vx = self.vy = 0.0
        self.dir = random.choice([-1, 1])
        self.walk_phase = 0.0
        now = time.time()
        self.state, self.state_until = "walk", now + random.uniform(4, 10)
        self.squash_v = 0.0
        self.sm_tilt = self.sm_lx = self.sm_ly = 0.0
        self.blink_at = now + random.uniform(2, 5)
        self.emote_text, self.emote_until, self.emote_start = None, 0.0, 0.0
        self.face_override, self.face_until = None, 0.0
        self.drop_to = None
        self.hover = False
        self.win = floating_window(NSMakeRect(self.x, self.y, self.W, self.H))
        self.view = CharView.alloc().initWithCritter_(self)
        self.win.setContentView_(self.view)
        self.win.orderFrontRegardless()

    @property
    def cx(self):
        return self.x + self.W / 2

    def set_scale(self, p):
        self.P, self.W, self.H = p, 16 * p, 13 * p
        self.win.setContentSize_((self.W, self.H))
        self.view.setFrame_(NSMakeRect(0, 0, self.W, self.H))

    def emote(self, text, color=ORANGE, sec=1.4):
        self.emote_text, self.emote_until, self.emote_start = (text, color), time.time() + sec, time.time()

    def feel(self, face, sec):
        self.face_override, self.face_until = face, time.time() + sec

    def airborne(self):
        return self.state in ("air", "jump") or self.vy > 0 or self.y > self.ground() + 0.5

    def ground(self):
        top = self.y + 2 if self.drop_to is None else min(self.y + 2, self.drop_to + 2)
        return self.world.ground(self.cx, top)

    def hop(self, vy=420.0, state="happy", sec=1.2):
        self.state, self.state_until = state, time.time() + sec
        self.vy, self.y = vy, self.y + 0.1

    def jump_to(self, tx, ty):
        dh = ty - self.y
        apex = max(dh, 0) + 40
        vy = math.sqrt(2 * GRAVITY * apex)
        t = vy / GRAVITY + math.sqrt(2 * (apex - dh) / GRAVITY)
        self.vx, self.vy = (tx - self.cx) / t, vy
        self.state, self.y = "jump", self.y + 0.1
        self.dir = 1 if tx > self.cx else -1

    def drop(self, ty):
        """창 위에서 아래 발판으로 뛰어내리기."""
        self.drop_to = ty
        self.state, self.vy = "jump", 200.0
        self.y += 0.1

    def physics(self, dt):
        """중력·착지. 착지 충격량을 돌려줌 (없으면 0)."""
        if self.state == "held":
            return 0.0
        g = self.ground()
        if not (self.y > g + 0.5 or self.vy > 0):
            self.y = g
            return 0.0
        if self.state not in ("air", "jump", "happy"):
            self.state = "air"  # 발판 끝에서 걸어 나가 떨어짐
        self.vy -= GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        lo, hi = self.world.xbounds(self.W)
        if not lo <= self.x <= hi:
            self.vx = -self.vx * 0.6
            self.x = max(lo, min(self.x, hi))
        top = self.world.ceiling(self.cx) - self.H
        if self.y > top:
            self.y, self.vy = top, -abs(self.vy) * 0.5
        g = self.ground()
        if self.y > g or self.vy > 0:
            return 0.0
        impact, self.y, self.drop_to = -self.vy, g, None
        self.squash_v = min(0.2, impact / 4000)
        if impact > 300 and self.state == "air":  # 던지면 통통
            self.vy, self.vx = impact * 0.4, self.vx * 0.7
            return impact
        self.vy = self.vx = 0.0
        if self.state in ("air", "jump"):
            self.state, self.state_until = "rest", time.time() + 1.0
        return impact

    def walk(self, dt, speed):
        self.x += self.dir * speed * dt
        lo, hi = self.world.xbounds(self.W)
        if not lo <= self.x <= hi:
            self.dir = -self.dir
            self.x = max(lo, min(self.x, hi))
        self.walk_phase += dt * 9 * speed / 55

    def chase(self, tx, ty, speed, dt, near):
        """(tx=목표 중심 x, ty=목표 발판 높이)까지 걸어가고, 높이가 다르면 점프/뛰어내림. 도착하면 True."""
        if abs(tx - self.cx) > near:
            self.state, self.state_until = "fetch", time.time() + 0.5
            self.dir = 1 if tx > self.cx else -1
            self.x += self.dir * min(speed * dt, abs(tx - self.cx) - near * 0.5)
            self.walk_phase += dt * 9 * speed / 55
            return False
        if ty > self.y + 12:
            self.jump_to(tx, ty)
            return False
        if ty < self.y - 12:
            self.drop(ty)
            return False
        return True

    def render(self):
        self.win.setFrameOrigin_((self.x, self.y))
        self.view.setNeedsDisplay_(True)

    def pose(self):
        now = time.time()
        st = self.state
        w = st in ("walk", "fetch")
        ph = self.walk_phase
        step = math.sin(ph)
        dangle = st in ("held", "air")
        typing = st == "work"
        breathe = 0.5 + 0.5 * math.sin(now * (1.2 if st == "sleep" else 2.2))
        m = NSEvent.mouseLocation()
        dx, dy = m.x - self.cx, m.y - (self.y + self.H / 2)
        d = math.hypot(dx, dy) or 1
        if st in ("work", "focus"):
            lx, ly = math.sin(now * (3 if typing else 0.8)) * self.P * 0.3, -self.P * 0.3
        elif d < 260 and st != "sleep":
            lx, ly = dx / d * self.P * 0.5, dy / d * self.P * 0.35
        elif st == "look":
            lx, ly = math.sin(now * 2.5) * self.P * 0.5, 0.0
        else:
            lx, ly = self.dir * self.P * 0.25, 0.0
        if st == "held":
            tilt = math.sin(now * 5) * 12
        elif st == "air":
            tilt = max(-30.0, min(30.0, -self.vx / 40))
        elif st == "jump":
            tilt = -self.dir * 10
        elif st == "happy":
            tilt = math.sin(now * 18) * 6
        elif w:
            tilt = -self.dir * 5 + math.sin(ph * 2) * 1.5
        else:
            tilt = 0.0
        a = 0.18
        self.sm_tilt += (tilt - self.sm_tilt) * a
        self.sm_lx += (lx - self.sm_lx) * a
        self.sm_ly += (ly - self.sm_ly) * a
        stretch = max(-0.15, min(0.15, self.vy / 3000)) if dangle or st in ("happy", "jump") else 0.0
        P = self.P
        # 표정
        if now < self.face_until:
            face = self.face_override
        elif st == "happy":
            face = "happy"
        elif st == "held":
            face = "surprised"
        elif st == "sleep":
            face = "sleep"
        elif st in ("work", "focus"):
            face = "work"
        elif self.blink_at <= now < self.blink_at + 0.12:
            face = "blink"
        elif self.owner.night() and st in ("rest", "look"):
            face = "sleepy"
        else:
            face = "normal"
        wave = self.hover or st == "look"
        if typing:  # 타닥타닥
            armL, armR = abs(math.sin(now * 14)) * P * 0.6, abs(math.cos(now * 14)) * P * 0.6
        elif dangle or st in ("happy", "jump"):
            armL = armR = P * 1.2
        else:
            armL = -step * P * 0.3 if w else 0.0
            armR = abs(math.sin(now * 9)) * P * 1.5 if wave else (step * P * 0.3 if w else 0.0)
        emote = self.emote_text if now < self.emote_until else self.owner.idle_emote(self)
        return {
            "legA": max(0.0, step) ** 1.5 * P * 0.9 if w else (P * 0.6 * (0.5 + 0.5 * math.sin(now * 12)) if dangle else 0.0),
            "legB": max(0.0, -step) ** 1.5 * P * 0.9 if w else (P * 0.6 * (0.5 - 0.5 * math.sin(now * 12)) if dangle else 0.0),
            "bob": abs(step) * P * 0.3 if w else (P * 0.8 if dangle else (abs(math.sin(now * 14)) * P * 0.15 if typing else 0.0)),
            "squash": max(0.8, min(1.15, 1.0 + stretch - self.squash_v - (0.04 * breathe if not w else 0))),
            "armL": armL, "armR": armR,
            "lookX": self.sm_lx, "lookY": self.sm_ly, "tilt": self.sm_tilt,
            "shadow": not self.airborne() and st != "held",
            "face": face, "emote": emote,
            "emoteRise": (now - self.emote_start) * 6 if now < self.emote_until else math.sin(now * 2) * 2,
        }


# ---------------------------------------------------------------- 장난감 (간식·공)
TOY = 30


class ToyView(NSView):
    def initWithToy_(self, t):
        self = objc.super(ToyView, self).initWithFrame_(NSMakeRect(0, 0, TOY, TOY))
        self.t = t
        return self

    def acceptsFirstMouse_(self, e):
        return True

    def mouseDown_(self, e):
        self.t.grab(NSEvent.mouseLocation())

    def mouseDragged_(self, e):
        self.t.move(NSEvent.mouseLocation())

    def mouseUp_(self, e):
        self.t.throw()

    def drawRect_(self, r):
        tf = NSAffineTransform.transform()
        tf.translateXBy_yBy_(TOY / 2, TOY / 2)
        tf.rotateByDegrees_(self.t.spin)
        tf.translateXBy_yBy_(-TOY / 2, -TOY / 2)
        tf.concat()
        NSString.stringWithString_(self.t.emoji).drawAtPoint_withAttributes_((2, 2), {NSFontAttributeName: NSFont.systemFontOfSize_(22)})


class Toy:
    def __init__(self, world, kind, x, y):
        self.world, self.kind = world, kind
        self.emoji = "🍪" if kind == "snack" else "⚾"
        self.bounce = 0.35 if kind == "snack" else 0.65
        self.x, self.y, self.vx, self.vy, self.spin = x, y, 0.0, 0.0, 0.0
        self.held, self.carried, self.hist = False, False, []
        self.waiting = False  # 물어다 준 뒤엔 다시 던져줄 때까지 기다림
        self.win = floating_window(NSMakeRect(x, y, TOY, TOY))
        self.view = ToyView.alloc().initWithToy_(self)
        self.win.setContentView_(self.view)
        self.win.orderFrontRegardless()

    @property
    def cx(self):
        return self.x + TOY / 2

    def grab(self, m):
        self.held, self.carried, self.waiting, self.hist = True, False, False, [(time.time(), m.x, m.y)]

    def move(self, m):
        self.hist = (self.hist + [(time.time(), m.x, m.y)])[-5:]
        self.x, self.y = m.x - TOY / 2, m.y - TOY / 2

    def throw(self):
        (t0, x0, y0), (t1, x1, y1) = self.hist[0], self.hist[-1]
        dt = max(t1 - t0, 1 / 60)
        self.vx = max(-2500.0, min(2500.0, (x1 - x0) / dt * 0.8))
        self.vy = max(-2500.0, min(2500.0, (y1 - y0) / dt * 0.8))
        self.held = False

    def settled(self):
        return not self.held and not self.carried and not self.waiting and abs(self.vy) < 1 and abs(self.vx) < 5 and self.y <= self.world.ground(self.cx, self.y + 2) + 0.5

    def physics(self, dt):
        if self.held or self.carried:
            return
        g = self.world.ground(self.cx, self.y + 2)
        if self.y > g + 0.5 or self.vy > 0:
            self.vy -= GRAVITY * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.spin -= self.vx * dt * 3
            lo, hi = self.world.xbounds(TOY)
            if not lo <= self.x <= hi:
                self.vx, self.x = -self.vx * 0.7, max(lo, min(self.x, hi))
            g = self.world.ground(self.cx, self.y + 2)
            if self.y <= g and self.vy <= 0:
                self.y = g
                self.vy = -self.vy * self.bounce if self.vy < -150 else 0.0
                self.vx *= 0.75
        else:
            self.y, self.vy = g, 0.0
            self.vx *= 0.9  # 굴러가다 멈춤
            self.x += self.vx * dt
            self.spin -= self.vx * dt * 3

    def render(self):
        self.win.setFrameOrigin_((self.x, self.y))
        self.view.setNeedsDisplay_(True)

    def close(self):
        self.win.orderOut_(None)


# ---------------------------------------------------------------- 말풍선·칩
class BubbleView(NSView):
    TAIL = 10

    def acceptsFirstMouse_(self, e):
        return True

    def drawRect_(self, r):
        b, t = self.bounds(), self.TAIL
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(1, t + 1, b.size.width - 2, b.size.height - t - 2), 14, 14)
        tx = self.tail_x
        tail = NSBezierPath.bezierPath()
        tail.moveToPoint_((tx - 9, t + 2))
        tail.lineToPoint_((tx, 1))
        tail.lineToPoint_((tx + 9, t + 2))
        tail.closePath()
        path.appendBezierPath_(tail)
        NSColor.whiteColor().setFill()
        path.fill()
        ORANGE.setStroke()
        path.setLineWidth_(2)
        path.stroke()
        NSColor.whiteColor().setFill()
        NSBezierPath.fillRect_(NSMakeRect(tx - 7.5, t, 15, 3))


class Pill(NSView):
    """첫 클릭부터 반응하는 둥근 버튼 (비활성 앱에서도 동작)."""

    def acceptsFirstMouse_(self, e):
        return True

    def hitTest_(self, p):
        return self if objc.super(Pill, self).hitTest_(p) else None

    def mouseDown_(self, e):
        if self.fn:
            self.fn()

    def drawRect_(self, r):
        b = self.bounds()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(0.5, 0.5, b.size.width - 1, b.size.height - 1),
                                                                     b.size.height / 2, b.size.height / 2)
        self.bg.setFill()
        path.fill()
        if self.border:
            self.border.setStroke()
            path.stroke()


def pill(text, fn, bg, fg, h=26, size=12, border=None):
    lb = label(text, size, fg, bold=True)
    lb.sizeToFit()
    lw, lh = lb.frame().size.width, lb.frame().size.height
    p = Pill.alloc().initWithFrame_(NSMakeRect(0, 0, lw + h * 0.85, h))
    p.fn, p.bg, p.border = fn, bg, border
    lb.setFrameOrigin_((h * 0.425, (h - lh) / 2))
    p.addSubview_(lb)
    return p


class Chip:
    """캐릭터 머리 위 작은 상태 표시 (지금 하는 작업)."""

    def __init__(self, size):
        self.size, self.text, self.win, self.shown = size, None, None, False

    def set(self, text):
        if text == self.text:
            return
        self.text = text
        if self.win:
            self.win.orderOut_(None)
            self.win = None
        if text:
            p = pill(text, None, rgb("#FFFFFF", 0.95), rgb("#333333"), h=self.size * 2, size=self.size, border=ORANGE)
            f = p.frame()
            self.win = floating_window(f)
            self.win.setIgnoresMouseEvents_(True)
            self.win.setContentView_(p)
            self.shown = False

    def place(self, cx, y, visible):
        if not self.win:
            return
        if visible != self.shown:
            self.shown = visible
            if visible:
                self.win.orderFrontRegardless()
            else:
                self.win.orderOut_(None)
        if visible:
            w = self.win.frame().size.width
            self.win.setFrameOrigin_((cx - w / 2, y))

    def close(self):
        self.set(None)


# ---------------------------------------------------------------- 메뉴 대상
class Ctl(NSObject):
    def initWithBuddy_(self, b):
        self = objc.super(Ctl, self).init()
        self.b = b
        return self

    def tick_(self, t):
        try:
            self.b.tick()
        except Exception:  # noqa: BLE001 - 한 프레임 오류로 앱이 멈추지 않게
            import traceback
            traceback.print_exc()

    def menuNeedsUpdate_(self, menu):
        menu.removeAllItems()
        self.b.build_menu(menu, status=True)

    def nextTip_(self, s):
        self.b.next_tip()

    def ask_(self, s):
        self.b.open_ask()

    def askSubmit_(self, s):
        self.b.submit_ask(s.stringValue())

    def snack_(self, s):
        self.b.spawn_toy("snack")

    def ball_(self, s):
        self.b.spawn_toy("ball")

    def follow_(self, s):
        self.b.follow = not self.b.follow
        self.b.main.emote("따라갈게!" if self.b.follow else "OK")

    def focus_(self, s):
        self.b.toggle_focus()

    def snooze_(self, s):
        self.b.snooze()

    def setModule_(self, s):
        self.b.module = s.tag() or None
        self.b.main.emote("OK!")
        self.b.next_tip()

    def toggleHidden_(self, s):
        self.b.manual_hidden = not self.b.manual_hidden

    def setInterval_(self, s):
        self.b.set_cfg("interval", s.tag())

    def setScale_(self, s):
        self.b.set_cfg("scale", s.tag())

    def setSpeed_(self, s):
        self.b.set_cfg("speed", s.tag())

    def toggleSound_(self, s):
        self.b.set_cfg("sound", not self.b.cfg["sound"])

    def toggleWindows_(self, s):
        self.b.set_cfg("windows", not self.b.cfg["windows"])

    def toggleActivity_(self, s):
        self.b.set_cfg("activity", not self.b.cfg["activity"])

    def quit_(self, s):
        NSApp().terminate_(None)


# ---------------------------------------------------------------- 본체
class Buddy:
    def __init__(self, tips, cfg):
        self.tips, self.cfg = tips, cfg
        random.shuffle(self.tips)
        self.idx = 0
        self.module = None
        self.ctl = Ctl.alloc().initWithBuddy_(self)
        self.world = World(cfg)
        v0 = self.world.vfs[0]
        self.main = Critter(self, self.world, cfg["scale"], random.uniform(v0.origin.x, v0.origin.x + v0.size.width - 16 * cfg["scale"]), ORANGE_HEX)
        self.minis = {}  # agent id -> Critter
        self.mini_chips = {}
        self.chip = Chip(11)
        self.toy = None
        self.follow = False
        self.focus_until = 0.0
        self.grab = None
        self.bubble, self.bubble_until = None, 0.0
        self.ask_win = None
        self.manual_hidden, self.hidden, self.fullscreen = False, False, False
        self.hover_since, self.hover_petted = 0.0, False
        now = time.time()
        self.next_tip_at = now + 5
        self.last = now
        self.next_slow = 0.0
        self.activity = Activity()
        self.active_since, self.was_idle, self.stretch_told, self.night_told = now, False, False, None
        self.status = NSStatusBar.systemStatusBar().statusItemWithLength_(-1)
        self.status.button().setImage_(icon_image(18))
        menu = NSMenu.alloc().init()
        menu.setDelegate_(self.ctl)
        self.status.setMenu_(menu)
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1 / 60, self.ctl, "tick:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)

    # ----- 설정
    def set_cfg(self, key, val):
        self.cfg[key] = val
        save_settings(self.cfg)
        if key == "scale":
            self.main.set_scale(val)
            for c in self.minis.values():
                c.set_scale(max(3, round(val * 0.55)))
        if key == "interval":
            self.next_tip_at = min(self.next_tip_at, time.time() + val)
        if key == "activity" and not val:
            self.chip.close()
            for aid in list(self.minis):
                self.remove_mini(aid)
        self.main.emote("OK!")

    def night(self):
        return 0 <= datetime.datetime.now().hour < 5

    def idle_emote(self, c):
        now = time.time()
        if c.state == "sleep":
            return ("z Z", GRAY)
        if c is self.main and self.focus_until:
            left = int(self.focus_until - now)
            return (f"{left // 60:02d}:{left % 60:02d}", GRAY)
        return None

    # ----- 마우스
    def press(self, c, m, clicks):
        self.grab = (c, (m.x - c.x, m.y - c.y), [(time.time(), m.x, m.y)], False)
        if clicks == 2:
            self.pet(c)

    def drag(self, c, m):
        if not self.grab:
            return
        _, off, hist, _ = self.grab
        hist = (hist + [(time.time(), m.x, m.y)])[-5:]
        self.grab = (c, off, hist, True)
        if c.state != "held":
            if c is self.main:
                self.close_bubble(reschedule=False)
            c.state = "held"
            c.emote("!")
            play(self.cfg, "Pop")
        c.x, c.y = m.x - off[0], m.y - off[1]

    def release(self, c):
        if not self.grab:
            return
        _, _, hist, moved = self.grab
        self.grab = None
        if not moved:
            if c is self.main:
                self.next_tip() if aws_tips else self.pet(c)
            else:
                self.show_mini_info(c)
            return
        (t0, x0, y0), (t1, x1, y1) = hist[0], hist[-1]
        dt = max(t1 - t0, 1 / 60)
        lim = 2500.0  # 순간 튄 마우스 값으로 화면 밖까지 날아가지 않게
        c.vx = max(-lim, min(lim, (x1 - x0) / dt))
        c.vy = max(-lim, min(lim, (y1 - y0) / dt))
        c.state = "air"
        fast = abs(c.vx) + abs(c.vy) > 600
        c.emote("으아아" if fast else "~")
        if fast:
            c.feel("surprised", 1.2)

    def pet(self, c):
        c.hop()
        c.emote("♥", rgb("#E0456B"))
        play(self.cfg, "Tink")

    # ----- 메뉴
    def build_menu(self, m, status=False):
        def item(title, sel, tag=0, on=False, target=None):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
            it.setTarget_(target or self.ctl)
            it.setTag_(tag)
            it.setState_(1 if on else 0)
            return it

        def sub(title, items):
            s = NSMenu.alloc().init()
            for it in items:
                s.addItem_(it)
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
            mi.setSubmenu_(s)
            return mi

        label_now = self.activity.label(time.time()) if self.cfg["activity"] else None
        if label_now:
            head = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Claude Code: {label_now}", None, "")
            head.setEnabled_(False)
            m.addItem_(head)
            for aid, c in self.minis.items():
                s = self.activity.subs.get(aid)
                if s:
                    it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"   └ {s['desc']}: {s['tail'].label or '준비 중'}", None, "")
                    it.setEnabled_(False)
                    m.addItem_(it)
            m.addItem_(NSMenuItem.separatorItem())
        if aws_tips:
            m.addItem_(item("💡 다음 팁", "nextTip:"))
            m.addItem_(item("💬 물어보기…", "ask:"))
            m.addItem_(sub("📚 모듈별 팁", [item("전체", "setModule:", 0, self.module is None)]
                           + [item(f"모듈 {k} · {n}", "setModule:", k, self.module == k) for k, n in aws_tips.MODULES.items()]))
            m.addItem_(NSMenuItem.separatorItem())
        m.addItem_(item("🍪 간식 주기", "snack:"))
        m.addItem_(item("⚾ 공놀이", "ball:"))
        m.addItem_(item("🐾 커서 따라오기", "follow:", on=self.follow))
        m.addItem_(item("⏰ 집중 타이머 취소" if self.focus_until else "⏰ 25분 집중 타이머", "focus:"))
        m.addItem_(item("💤 30분 조용히 (재우기)", "snooze:"))
        m.addItem_(NSMenuItem.separatorItem())
        c = self.cfg
        tip_gap = [sub("팁 간격", [item(n, "setInterval:", v, c["interval"] == v) for n, v in
                               (("30초", 30), ("1분", 60), ("3분", 180), ("5분", 300), ("10분", 600))])] if aws_tips else []
        m.addItem_(sub("⚙️ 설정", tip_gap + [
            sub("크기", [item(n, "setScale:", v, c["scale"] == v) for n, v in (("작게", 4), ("보통", 6), ("크게", 8))]),
            sub("걷는 속도", [item(n, "setSpeed:", v, c["speed"] == v) for n, v in (("느리게", 35), ("보통", 55), ("빠르게", 85))]),
            item("소리", "toggleSound:", on=c["sound"]),
            item("창 위로 올라가기", "toggleWindows:", on=c["windows"]),
            item("Claude Code 작업 보기", "toggleActivity:", on=c["activity"]),
        ]))
        if status:
            m.addItem_(item("캐릭터 보이기" if self.manual_hidden else "캐릭터 숨기기", "toggleHidden:"))
        m.addItem_(NSMenuItem.separatorItem())
        m.addItem_(item("종료", "quit:"))
        return m

    # ----- 장난감·모드
    def spawn_toy(self, kind):
        if self.toy:
            self.toy.close()
        m = NSEvent.mouseLocation()
        self.toy = Toy(self.world, kind, m.x - TOY / 2, m.y - TOY / 2)
        self.main.emote("!!")

    def toggle_focus(self):
        c = self.main
        if self.focus_until:
            self.focus_until = 0.0
            c.state, c.state_until = "rest", time.time() + 1
            c.emote("취소!", GRAY)
        else:
            self.close_bubble(reschedule=False)
            self.focus_until = time.time() + 25 * 60
            c.emote("집중!")

    def snooze(self):
        self.close_bubble(reschedule=False)
        self.next_tip_at = time.time() + 30 * 60
        self.main.state, self.main.state_until = "sleep", time.time() + 30 * 60

    # ----- 미니 (서브에이전트)
    def add_mini(self, aid):
        i = len(self.minis)
        c = Critter(self, self.world, max(3, round(self.cfg["scale"] * 0.55)),
                    self.main.x + random.uniform(-40, 40), MINI_COLORS[i % len(MINI_COLORS)], mini=True)
        c.y = self.main.y
        c.hop(380, "happy", 0.8)
        c.emote("뿅!")
        c.side = (1 if i % 2 == 0 else -1) * (1 + i // 2)
        c.done_at = None
        self.minis[aid] = c
        self.mini_chips[aid] = Chip(9)
        play(self.cfg, "Pop")

    def remove_mini(self, aid):
        c = self.minis.pop(aid)
        c.win.orderOut_(None)
        self.mini_chips.pop(aid).close()

    def show_mini_info(self, c):
        aid = next((a for a, v in self.minis.items() if v is c), None)
        s = self.activity.subs.get(aid)
        if s:
            self.show({"module": 0, "head": f"👥 서브에이전트 · {s['desc']}",
                       "text": f"지금: {s['tail'].label or '준비 중'}"}, anchor=c)

    # ----- 매 프레임
    def tick(self):
        now = time.time()
        dt = min(now - self.last, 0.05)
        self.last = now
        self.world.refresh(now)
        if now >= self.next_slow:
            self.next_slow = now + 1.0
            self.slow_tick(now)
        hide = self.manual_hidden or self.fullscreen
        if hide != self.hidden:
            self.hidden = hide
            for w in self.all_windows():
                if hide:
                    w.orderOut_(None)
                else:
                    w.orderFrontRegardless()
            for ch in [self.chip, *self.mini_chips.values()]:
                ch.shown = False
        if self.hidden:
            return

        m = NSEvent.mouseLocation()
        c = self.main
        f = c.win.frame()
        hovering = f.origin.x <= m.x <= f.origin.x + c.W and f.origin.y <= m.y <= f.origin.y + c.H * 0.75 and not self.grab
        if hovering and not c.hover:
            self.hover_since, self.hover_petted = now, False
        c.hover = hovering and c.state in ("walk", "rest", "look", "work")
        if c.hover and not self.hover_petted and now - self.hover_since > 2.5:
            self.hover_petted = True
            self.pet(c)

        self.brain(now, dt, m)
        impact = c.physics(dt)
        if impact > 1400:
            c.feel("sad", 1.6)
            c.emote("아야..", GRAY)
        elif impact > 600:
            play(self.cfg, "Bottle")
        c.squash_v = max(0.0, c.squash_v - dt * 0.8)
        if now > c.blink_at + 0.12:
            c.blink_at = now + random.uniform(2.5, 6)
        c.render()

        for aid, mc in list(self.minis.items()):
            self.mini_brain(aid, mc, now, dt)
            mc.physics(dt)
            mc.squash_v = max(0.0, mc.squash_v - dt * 0.8)
            if now > mc.blink_at + 0.12:
                mc.blink_at = now + random.uniform(2.5, 6)
            mc.render()
            s = self.activity.subs.get(aid)
            chip = self.mini_chips.get(aid)
            if chip:
                chip.set((s["tail"].label or "준비 중") if s and not mc.done_at else None)
                chip.place(mc.cx, mc.y + mc.H, mc.state != "held")

        if self.toy:
            if self.toy.carried:
                self.toy.x, self.toy.y = c.cx - TOY / 2, c.y + c.H * 0.62
            self.toy.physics(dt)
            self.toy.render()

        if self.bubble and now > self.bubble_until:
            self.close_bubble()
        if aws_tips and not self.bubble and now > self.next_tip_at and c.state in ("walk", "rest", "look"):
            self.show()
        self.chip.place(c.cx, c.y + c.H, not self.bubble and c.state != "held")

    def all_windows(self):
        ws = [self.main.win] + [m.win for m in self.minis.values()]
        ws += [ch.win for ch in [self.chip, *self.mini_chips.values()] if ch.win]
        if self.toy:
            ws.append(self.toy.win)
        if self.bubble:
            ws.append(self.bubble)
        return ws

    def slow_tick(self, now):
        """1초마다: 전체화면 감지, Claude Code 작업, 자리 비움·밤 반응."""
        self.fullscreen = self.world.fullscreen_front()
        c = self.main
        if self.cfg["activity"]:
            self.activity.poll(now)
            self.chip.set(self.activity.label(now))
            subs = self.activity.active_subs()
            for aid, s in subs.items():
                if aid not in self.minis and not s["finished"] and len(self.minis) < MAX_MINIS:
                    self.add_mini(aid)
                elif aid in self.minis and s["finished"] and self.minis[aid].done_at is None:
                    mc = self.minis[aid]
                    mc.done_at = now
                    mc.hop(420, "happy", 1.5)
                    mc.emote("완료!", rgb("#2E7D32"), 2)
                    play(self.cfg, "Glass")
            for aid in [a for a, mc in self.minis.items() if a not in subs]:
                self.remove_mini(aid)

        idle = CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateHIDSystemState, kCGAnyInputEventType)
        if idle > 300:
            self.active_since = now
            if not self.was_idle and c.state in ("walk", "rest", "look") and not self.focus_until:
                self.was_idle = True
                c.state, c.state_until = "sleep", now + 3600
        elif self.was_idle and idle < 2:
            self.was_idle = False
            c.state, c.state_until = "rest", now + 1
            c.feel("surprised", 0.8)
            c.hop(380, "happy", 1.0)
            c.emote("어서와요!")
        if now - self.active_since > 50 * 60 and not self.bubble and not self.focus_until:
            self.active_since = now
            self.show({"module": 0, "head": "🙆 쉬는 시간", "text": "50분째 쉬지 않고 달리는 중이에요! 일어나서 기지개 한 번 켜고 물 한 잔 마셔요."})
        today = datetime.date.today()
        if self.night() and self.night_told != today and not self.bubble:
            self.night_told = today
            self.show({"module": 0, "head": "🌙 늦은 밤", "text": f"벌써 새벽 {datetime.datetime.now().hour}시예요. 잠도 공부예요. 오늘은 여기까지 할까요?"})

    def brain(self, now, dt, m):
        c = self.main
        if c.state in ("held", "air", "jump") or (c.state == "happy" and (now < c.state_until or c.airborne())):
            return
        if c.state == "happy":
            c.state = "rest"
        speed = self.cfg["speed"]
        toy = self.toy
        if self.bubble:
            if c.state in ("walk", "fetch"):
                c.state = "rest"
            return
        if toy and toy.carried:  # 공 물고 커서한테 돌아오기
            ty = self.world.ground(m.x, m.y)
            if c.chase(m.x, ty, speed * 2, dt, 30):
                toy.carried, toy.waiting = False, True
                toy.vy, toy.vx = 250.0, c.dir * 60
                c.emote("또 던져줘!")
                c.state = "look"
            return
        if toy and toy.settled():
            if c.chase(toy.cx, toy.y, speed * 2.4, dt, 8):
                if toy.kind == "snack":
                    toy.close()
                    self.toy = None
                    c.hop()
                    c.emote("냠냠 ♥", rgb("#E0456B"), 1.8)
                    play(self.cfg, "Bottle")
                else:
                    toy.carried = True
                    c.emote("잡았다!")
                    play(self.cfg, "Ping")
            return
        if self.follow:
            if c.chase(m.x, self.world.ground(m.x, m.y), speed * 1.8, dt, 45):
                c.state = "look"
            return
        if self.focus_until:
            c.state = "focus"
            if now >= self.focus_until:
                self.focus_until = 0.0
                c.hop()
                play(self.cfg, "Glass")
                self.show({"module": 0, "head": "⏰ 25분 집중 끝!", "text": "수고했어요! 5분 쉬고 물 한 잔 마시고 다시 달려요 ☕"})
            return
        if self.cfg["activity"] and self.activity.busy(now) and c.state != "sleep":
            if c.state != "work":
                c.state = "work"
            return
        if c.state == "work":
            c.state, c.state_until = "rest", now + 1.5
            c.hop(300, "happy", 0.6)
        if c.hover:
            return
        if c.state == "walk":
            c.walk(dt, speed)
        if now > c.state_until:  # 다음 행동 고르기
            if c.state == "sleep":
                c.emote("!")
            weights = [5, 2, 2, 3 if self.night() else 1, 2 if self.cfg["windows"] else 0]
            nxt = random.choices(["walk", "rest", "look", "sleep", "climb"], weights)[0]
            if nxt == "climb":
                plat = self.world.platform_above(c.cx, c.y)
                if plat:
                    c.jump_to(random.uniform(plat[0] + 30, plat[1] - 30), plat[2])
                    return
                nxt = "walk"
            c.state = nxt
            c.state_until = now + {"walk": random.uniform(5, 14), "rest": random.uniform(2, 4),
                                   "look": random.uniform(2, 3), "sleep": random.uniform(8, 15)}[nxt]
            if nxt == "walk" and random.random() < 0.4:
                c.dir = -c.dir

    def mini_brain(self, aid, mc, now, dt):
        if mc.state in ("held", "air", "jump") or (mc.state == "happy" and (now < mc.state_until or mc.airborne())):
            return
        if mc.done_at:  # 끝난 미니는 손 흔들고 퇴장
            mc.walk(dt, 90)
            mc.state = "walk"
            if now - mc.done_at > 5:
                self.remove_mini(aid)
            return
        main = self.main
        tx = main.cx + mc.side * (main.W * 0.55 + mc.W * 0.7)
        if mc.chase(tx, main.y, self.cfg["speed"] * 1.6, dt, 10):
            mc.state = "work"
            mc.dir = 1 if main.cx > mc.cx else -1

    # ----- 말풍선
    def close_bubble(self, reschedule=True):
        if self.bubble:
            self.bubble.orderOut_(None)
            self.bubble = None
        if reschedule:
            self.next_tip_at = time.time() + self.cfg["interval"]

    def next_tip(self):
        self.close_bubble(reschedule=False)
        if self.main.state == "sleep":
            self.main.state = "rest"
        self.show()

    def show(self, t=None, anchor=None, extra=None):
        """t가 없으면 다음 팁. extra=[(버튼 글자, 함수)]로 버튼 교체."""
        self.close_bubble(reschedule=False)
        c = anchor or self.main
        if t is None:
            pool = [x for x in self.tips if self.module in (None, x["module"])]
            t = pool[self.idx % len(pool)]
            self.idx += 1
            play(self.cfg, "Pop")
        if c is self.main and not c.airborne() and c.state in ("walk", "rest", "look", "work", "fetch"):
            c.hop(300, "happy", 0.6)
        c.emote("!")
        pad, inner = 16, BUBBLE_W - 32
        head = label(t["head"] if t["head"][:1] in "💡👥⏰🙆🌙💬🔍" else f"💡 {t['head']}", 12, ORANGE, bold=True, width=inner)
        body = label(t["text"], 14, rgb("#222222"), width=inner)
        hh, th = head.fittingSize().height, body.fittingSize().height
        buttons = extra or [("다음 팁 ▶", self.next_tip)]
        pills = [pill(txt, fn, ORANGE, NSColor.whiteColor()) for txt, fn in buttons]
        pills.append(pill("닫기", self.close_bubble, rgb("#F1EDE8"), rgb("#666666")))
        tail = BubbleView.TAIL
        h = tail + pad + 26 + 10 + th + 6 + hh + pad
        v = self.world.screen_at(c.cx, c.y)
        bx = max(v.origin.x + 8, min(c.cx - BUBBLE_W / 2, v.origin.x + v.size.width - BUBBLE_W - 8))
        by = min(c.y + c.H + 2, v.origin.y + v.size.height - h)
        win = floating_window(NSMakeRect(bx, by, BUBBLE_W, h))
        bv = BubbleView.alloc().initWithFrame_(NSMakeRect(0, 0, BUBBLE_W, h))
        bv.tail_x = max(20, min(c.cx - bx, BUBBLE_W - 20))
        win.setContentView_(bv)
        y, right = tail + pad, BUBBLE_W - pad
        for p in reversed(pills):
            pw = p.frame().size.width
            p.setFrameOrigin_((right - pw, y))
            right -= pw + 6
            bv.addSubview_(p)
        y += 36
        body.setFrame_(NSMakeRect(pad, y, inner, th))
        bv.addSubview_(body)
        head.setFrame_(NSMakeRect(pad, y + th + 6, inner, hh))
        bv.addSubview_(head)
        win.setAlphaValue_(0.0)
        win.orderFrontRegardless()
        win.animator().setAlphaValue_(1.0)
        self.bubble = win
        self.bubble_until = time.time() + SHOW_SEC

    # ----- 물어보기
    def open_ask(self):
        self.close_bubble(reschedule=False)
        if self.ask_win:
            self.ask_win.orderOut_(None)
        c = self.main
        w, h = 340, 64
        v = self.world.screen_at(c.cx, c.y)
        x = max(v.origin.x + 8, min(c.cx - w / 2, v.origin.x + v.size.width - w - 8))
        win = floating_window(NSMakeRect(x, min(c.y + c.H + 4, v.origin.y + v.size.height - h), w, h), KeyWindow)
        win.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameAqua))  # 흰 말풍선이라 항상 라이트 모드
        bv = BubbleView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        bv.tail_x = max(20, min(c.cx - x, w - 20))
        win.setContentView_(bv)
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(14, 22, w - 28, 26))
        field.setPlaceholderString_("AWS 궁금한 거 물어보세요 (예: S3 Glacier 차이)  ⏎")
        field.setFont_(NSFont.systemFontOfSize_(13))
        field.setTextColor_(rgb("#222222"))  # 다크 모드에서 흰 글자로 안 보이던 문제
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        field.setFocusRingType_(1)  # 포커스 테두리 없음
        field.setTarget_(self.ctl)
        field.setAction_("askSubmit:")
        bv.addSubview_(field)
        win.makeKeyAndOrderFront_(None)
        win.makeFirstResponder_(field)
        try:
            NSApp().activate()
        except AttributeError:
            NSApp().activateIgnoringOtherApps_(True)
        self.ask_win = win
        c.state, c.state_until = "look", time.time() + 5
        c.emote("?")

    def submit_ask(self, q):
        if self.ask_win:
            self.ask_win.orderOut_(None)
            self.ask_win = None
        q = q.strip()
        if not q:
            return
        found = aws_tips.search_tips(self.tips, q, 5)
        c = self.main
        c.emote("음…", GRAY, 30)
        c.feel("work", 30)

        def work():
            answer = aws_tips.ask_claude(q, found)
            AppHelper.callAfter(self.answer, q, found, answer)

        threading.Thread(target=work, daemon=True).start()

    def answer(self, q, found, answer):
        c = self.main
        c.emote_until = c.face_until = 0
        if answer:
            self.show({"module": 0, "head": f"💬 {q[:40]}", "text": answer})
        elif found:
            results = list(found[:3])

            def show_i(i):
                t = results[i]
                more = [(f"다른 결과 ({(i + 1) % len(results) + 1}/{len(results)}) ▶", lambda: show_i((i + 1) % len(results)))] if len(results) > 1 else []
                self.show({"module": 0, "head": f"🔍 {t['head']}", "text": t["text"]}, extra=more or [("다음 팁 ▶", self.next_tip)])

            show_i(0)
        else:
            c.feel("sad", 1.5)
            self.show({"module": 0, "head": f"💬 {q[:40]}", "text": "관련 팁을 못 찾았어요 😅 다른 키워드(서비스 이름 등)로 물어봐 주세요."})


# ---------------------------------------------------------------- 아이콘
class _Still:
    """창 없이 고정 포즈로 그리기 (아이콘용)."""

    def __init__(self, p):
        self.P, self.W, self.H = p, 16 * p, 13 * p
        self.cols = (rgb(ORANGE_HEX), rgb(tone(ORANGE_HEX, 1.25)), rgb(tone(ORANGE_HEX, 0.82)))

    def pose(self):
        return {"legA": 0, "legB": 0, "bob": 0, "squash": 1, "armL": 0, "armR": self.P * 1.2, "lookX": 0, "lookY": 0,
                "tilt": 0, "shadow": False, "face": "normal", "emote": None, "emoteRise": 0}


def icon_image(px):
    c = _Still(px / 16)
    img = NSImage.alloc().initWithSize_((px, px))
    img.lockFocus()
    tf = NSAffineTransform.transform()
    tf.translateXBy_yBy_(0, (px - c.H) / 2)
    tf.concat()
    draw_critter(c, c.pose())
    img.unlockFocus()
    return img


def write_icon(path, px=1024):
    img = icon_image(px)
    rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
    rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None).writeToFile_atomically_(str(path), True)


def main():
    ap = argparse.ArgumentParser(description="AWS 시험 팁 + Claude Code 작업 상황을 보여주는 Claude 데스크톱 펫")
    ap.add_argument("--icon", help="아이콘 PNG만 만들고 종료 (make_app.sh용)")
    args = ap.parse_args()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # Dock 아이콘 없이
    if args.icon:
        write_icon(args.icon)
        return
    buddy = Buddy(aws_tips.load_tips() if aws_tips else [], load_settings())  # noqa: F841 (앱이 도는 동안 참조 유지)
    app.run()


if __name__ == "__main__":
    main()
