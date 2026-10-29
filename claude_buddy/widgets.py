"""말풍선, 알약 버튼, 머리 위 상태 칩."""

import objc
from AppKit import NSBezierPath, NSColor, NSMakeRect, NSView

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
            w = self.win.frame().size.width
            self.win.setFrameOrigin_((cx - w / 2, y))

    def close(self):
        self.set(None)
