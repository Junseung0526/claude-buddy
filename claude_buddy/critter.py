"""캐릭터 그리기(draw_critter)와 물리·행동(Critter). 메인과 서브에이전트 미니가 함께 쓴다."""

import math
import random
import time

import objc
from AppKit import (
    NSAffineTransform, NSBezierPath, NSEvent, NSFont, NSFontAttributeName, NSForegroundColorAttributeName, NSMakeRect, NSMenu, NSString, NSView,
)

from .config import GRAVITY
from .gfx import EYE, HEART, HEART_PX, ORANGE, PINK, TEAR, fill, floating_window, rgb, tone
from .menu import build_menu


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
        b = self.c.owner
        b.menu_open = True  # popUp은 메뉴가 닫혀야 반환됨
        NSMenu.popUpContextMenu_withEvent_forView_(build_menu(b, NSMenu.alloc().init()), e, self)
        b.menu_open = False

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
    if s["emote"] and s["emote"][0] == HEART:
        hp = max(1.5, P * 0.45)
        hx, hy = min(bx + bw + P * 0.5 - 3.5 * hp, W - 7 * hp), by + bh + P * 0.6 + s["emoteRise"]
        for r, row in enumerate(HEART_PX):
            for col, ch in enumerate(row):
                if ch == "X":
                    fill(hx + col * hp, hy + (len(HEART_PX) - 1 - r) * hp, hp, hp, s["emote"][1])
    elif s["emote"]:
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
