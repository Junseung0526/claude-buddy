"""간식·공 장난감."""

import time

import objc
from AppKit import NSAffineTransform, NSBezierPath, NSColor, NSEvent, NSMakeRect, NSView

from .config import GRAVITY
from .gfx import fill, floating_window, rgb


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
        r = NSMakeRect(4, 4, TOY - 8, TOY - 8)
        oval = NSBezierPath.bezierPathWithOvalInRect_(r)
        if self.t.kind == "snack":  # 초코칩 쿠키
            rgb("#C98A4B").setFill()
            oval.fill()
            rgb("#A86E37").setStroke()
            oval.setLineWidth_(1.5)
            oval.stroke()
            for x, y in ((9, 16), (16, 20), (18, 11), (11, 9), (21, 16)):
                fill(x, y, 3, 3, rgb("#4A2C17"))
        else:  # 야구공
            NSColor.whiteColor().setFill()
            oval.fill()
            rgb("#BBBBBB").setStroke()
            oval.setLineWidth_(1.2)
            oval.stroke()
            rgb("#D0343A").setStroke()
            for sx in (1, -1):
                seam = NSBezierPath.bezierPath()
                cx = TOY / 2 + sx * 9
                seam.moveToPoint_((cx, 6))
                seam.curveToPoint_controlPoint1_controlPoint2_((cx, TOY - 6), (TOY / 2 - sx * 1, 12), (TOY / 2 - sx * 1, TOY - 12))
                seam.setLineWidth_(1.4)
                seam.stroke()


class Toy:
    def __init__(self, world, kind, x, y):
        self.world, self.kind = world, kind
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
        self.win.setFrameOrigin_((round(self.x), round(self.y)))
        if round(self.spin) != getattr(self, "drawn_spin", None):  # 배터리: 돌 때만 다시 그림
            self.drawn_spin = round(self.spin)
            self.view.setNeedsDisplay_(True)

    def close(self):
        self.win.orderOut_(None)
