"""모니터 영역, 다른 앱 창의 윗변(발판), 전체화면 여부를 계산한다."""

import os
import random

from AppKit import NSScreen, NSWorkspace
from Quartz import (
    CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowListExcludeDesktopElements, kCGWindowListOptionOnScreenOnly,
)


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
