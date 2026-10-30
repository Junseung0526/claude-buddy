"""색·그리기 도우미, 떠 있는 투명 창, 라벨, 효과음."""

import json
import subprocess

from AppKit import (
    NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont, NSMakeRect, NSSound, NSStatusWindowLevel, NSTextField, NSWindow, NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowCollectionBehaviorStationary, NSWindowStyleMaskBorderless,
)


def rgb(h, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(int(h[1:3], 16) / 255, int(h[3:5], 16) / 255, int(h[5:7], 16) / 255, a)


def tone(h, k):
    c = [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    c = [min(255, int(v * k)) if k < 1 else min(255, int(v + (255 - v) * (k - 1))) for v in c]
    return "#%02X%02X%02X" % tuple(c)


ORANGE_HEX = "#D97757"
ORANGE, EYE, PINK, TEAR, GRAY = rgb(ORANGE_HEX), rgb("#1F1F1F"), rgb("#F2A0A8", 0.8), rgb("#7EC8F2"), rgb("#8A8A8A")
HEART = "<3"  # 이모트 대신 픽셀 하트를 그리라는 표시
HEART_PX = [".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..."]
# 다른 에이전트 캐릭터: 몸 색, 머리 위 표식(픽셀), 표식 색
STAR_PX = ["...X...", "...X...", "..XXX..", "XXXXXXX", "..XXX..", "...X...", "...X..."]
RING_PX = [".XXX.", "X...X", "X...X", "X...X", ".XXX."]
CLAUDE_PX = ["X.X.X", ".XXX.", "XXXXX", ".XXX.", "X.X.X"]
AGENT_LOOKS = {
    "claude": ("#D97757", CLAUDE_PX, "#9C4A2F"),  # 동시에 도는 다른 Claude Code 세션: 주황 몸 + 별표
    "gemini": ("#4C8DF6", STAR_PX, "#B9A6FF"),  # Antigravity·Gemini: 파란 몸 + 반짝이
    "gpt": ("#10A37F", RING_PX, "#FFFFFF"),     # Codex·GPT: 초록 몸 + 고리
}
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


def notify(cfg, title, text):
    """macOS 알림 센터에 알림 (osascript라 앱 서명·권한 요청 없이 됨)."""
    if cfg["notify"]:
        script = f"display notification {json.dumps(text, ensure_ascii=False)} with title {json.dumps(title, ensure_ascii=False)}"
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def play(cfg, name):
    if cfg["sound"]:
        s = NSSound.soundNamed_(name)
        if s:
            s.setVolume_(0.25)
            s.play()
