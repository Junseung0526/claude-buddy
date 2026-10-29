"""말풍선, 알약 버튼, 머리 위 상태 칩, 사용량 창."""

import objc
from AppKit import NSBezierPath, NSColor, NSFont, NSFontAttributeName, NSForegroundColorAttributeName, NSMakeRect, NSString, NSView

from .activity import DONE_LABEL
from .gfx import ORANGE, floating_window, label, rgb


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
        if self.dot:
            d = b.size.height * 0.3
            self.dot.setFill()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(b.size.height * 0.425, (b.size.height - d) / 2, d, d)).fill()


def pill(text, fn, bg, fg, h=26, size=12, border=None, dot=None):
    lb = label(text, size, fg, bold=True)
    lb.sizeToFit()
    lw, lh = lb.frame().size.width, lb.frame().size.height
    pad = h * 0.425
    lead = h * 0.4 if dot else 0  # 상태 점 자리
    p = Pill.alloc().initWithFrame_(NSMakeRect(0, 0, lw + pad * 2 + lead, h))
    p.fn, p.bg, p.border, p.dot = fn, bg, border, dot
    lb.setFrameOrigin_((pad + lead, (h - lh) / 2))
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
            dot = rgb("#2E9E5B") if text == DONE_LABEL else ORANGE
            p = pill(text, None, rgb("#FFFFFF", 0.95), rgb("#333333"), h=self.size * 2, size=self.size, border=ORANGE, dot=dot)
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
            pos = (round(cx - self.win.frame().size.width / 2), round(y))
            if pos != getattr(self, "pos", None):  # 배터리: 움직였을 때만
                self.pos = pos
                self.win.setFrameOrigin_(pos)

    def close(self):
        self.set(None)


INK, INK2, MUTED, LINE = rgb("#222222"), rgb("#555555"), rgb("#8A8A8A"), rgb("#E6E2DC")


def text(s, x, y, size, color, bold=False, right=False):
    """뒤집힌 좌표(위가 0)에서 (x, y)에 글자. right=True면 x가 오른쪽 끝."""
    attrs = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size),
             NSForegroundColorAttributeName: color}
    ns = NSString.stringWithString_(s)
    w = ns.sizeWithAttributes_(attrs).width
    ns.drawAtPoint_withAttributes_((x - w if right else x, y), attrs)
    return w


class UsageView(NSView):
    """사용량 창: 오늘 숫자 4개, 최근 7일 출력 막대, 오늘 프로젝트별 출력."""

    def isFlipped(self):
        return True

    def setData_(self, data):
        self.data = data
        self.removeAllToolTips()
        self.setNeedsDisplay_(True)

    def bar_rects(self):
        _, by_day, _ = self.data
        w = self.bounds().size.width
        n, top, bottom = len(by_day), 158, 278
        slot = (w - 48) / n
        peak = max([v for _, v in by_day] + [1])
        for i, (d, v) in enumerate(by_day):
            h = max(2, (bottom - top) * v / peak) if v else 0
            yield i, d, v, NSMakeRect(24 + i * slot + slot * 0.2, bottom - h, slot * 0.6, h), slot

    def view_stringForToolTip_point_userData_(self, view, tag, point, data):
        for i, d, v, r, slot in self.bar_rects():
            if 24 + i * slot <= point.x < 24 + (i + 1) * slot:
                return f"{d.month}월 {d.day}일 · 출력 {v:,} 토큰"
        return ""

    def drawRect_(self, r):
        from .usage import fmt
        (sessions, replies, inp, cached, out), by_day, projects = self.data
        w = self.bounds().size.width
        NSColor.whiteColor().setFill()
        NSBezierPath.fillRect_(self.bounds())
        # 오늘 숫자
        tiles = (("오늘 출력", fmt(out)), ("오늘 입력", fmt(inp)), ("세션", f"{sessions}개"), ("응답", f"{replies}번"))
        tw = (w - 48) / len(tiles)
        for i, (k, v) in enumerate(tiles):
            text(k, 24 + i * tw, 18, 11, MUTED)
            text(v, 24 + i * tw, 34, 22, INK, bold=True)
        text(f"입력은 캐시 읽기 {fmt(cached)} 토큰을 뺀 값", 24, 70, 10, MUTED)
        # 최근 7일 출력 막대 (한 계열이라 범례 없이 제목으로)
        text("최근 7일 출력 토큰", 24, 104, 12, INK2, bold=True)
        LINE.setFill()
        NSBezierPath.fillRect_(NSMakeRect(24, 278, w - 48, 1))
        bars = list(self.bar_rects())
        peak_i = max(bars, key=lambda b: b[2])[0]
        self.removeAllToolTips()
        for i, d, v, rect, slot in bars:
            today = i == len(bars) - 1
            ORANGE.setFill()
            if rect.size.height:
                # 위 끝만 둥글게: 둥근 사각형 + 아래 절반을 덮는 사각형
                path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, 4, 4)
                path.appendBezierPathWithRect_(NSMakeRect(rect.origin.x, rect.origin.y + rect.size.height / 2, rect.size.width, rect.size.height / 2))
                path.fill()  # 한 번에 채워야 이음새가 안 보임
            cx = rect.origin.x + rect.size.width / 2
            day = "오늘" if today else f"{d.month}/{d.day}"
            text(day, cx + _half(day, 10, today), 284, 10, INK if today else MUTED, bold=today)
            if (today or i == peak_i) and v:  # 값은 오늘과 가장 많은 날만 (나머지는 툴팁)
                s = fmt(v)
                text(s, cx + _half(s, 10, True), rect.origin.y - 16, 10, INK, bold=True)
            self.addToolTipRect_owner_userData_(NSMakeRect(24 + i * slot, 150, slot, 150), self, None)
        # 오늘 프로젝트별
        text("오늘 프로젝트별 출력", 24, 318, 12, INK2, bold=True)
        if not projects:
            text("오늘은 아직 기록이 없어요", 24, 342, 12, MUTED)
        top = projects[0][1] if projects else 1
        for k, (name, v) in enumerate(projects[:4]):
            y = 342 + k * 24
            text(name if len(name) <= 34 else "…" + name[-33:], 24, y, 12, INK)
            text(fmt(v), w - 24, y, 12, INK2, right=True)
            LINE.setFill()
            NSBezierPath.fillRect_(NSMakeRect(24, y + 17, w - 48, 3))
            ORANGE.setFill()
            NSBezierPath.fillRect_(NSMakeRect(24, y + 17, max(2, (w - 48) * v / top), 3))


def _half(s, size, bold):
    """가운데 맞춤용: 글자 폭의 절반만큼 왼쪽으로."""
    f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    return -NSString.stringWithString_(s).sizeWithAttributes_({NSFontAttributeName: f}).width / 2
