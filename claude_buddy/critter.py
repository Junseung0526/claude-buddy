"""캐릭터 그리기(draw_critter)와 물리·행동(Critter). 메인과 서브에이전트 미니가 함께 쓴다."""

import math
import random
import time

import objc
from AppKit import (
    NSAffineTransform, NSBezierPath, NSEvent, NSFont, NSFontAttributeName, NSForegroundColorAttributeName, NSGraphicsContext, NSMakeRect,
    NSMenu, NSString, NSView,
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
        draw_critter(self.c, self.c.cur_pose or self.c.pose())


def draw_critter(c, s):
    P, W = c.P, c.W
    body, hi, lo = c.cols
    base = P * 0.7
    if s["shadow"]:
        rgb("#000000", 0.16).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(W / 2 - 4.5 * P, 0, 9 * P, P * 0.9)).fill()
    NSGraphicsContext.saveGraphicsState()  # 기울기·회전은 몸에만, 머리 위 글자는 똑바로
    tf = NSAffineTransform.transform()  # 발끝 중심으로 기울이기
    tf.translateXBy_yBy_(W / 2, base)
    tf.rotateByDegrees_(s["tilt"])
    tf.translateXBy_yBy_(-W / 2, -base)
    tf.concat()
    if s.get("spin"):  # 공중제비: 몸 가운데를 축으로
        cy = base + 4 * P + s["bob"]
        sp = NSAffineTransform.transform()
        sp.translateXBy_yBy_(W / 2, cy)
        sp.rotateByDegrees_(s["spin"])
        sp.translateXBy_yBy_(-W / 2, -cy)
        sp.concat()
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
        elif face in ("sleep", "blink", "yawn"):
            fill(ex, ey + P * 0.45, P, P * 0.25, EYE)
        elif face in ("work", "focus"):
            fill(ex, ey + P * 0.1, P, P * 0.6, EYE)
        elif face == "sleepy":
            fill(ex, ey + P * 0.3, P, P * 0.55, EYE)
        else:
            fill(ex, ey, P, P * 1.25, EYE)
    if face == "surprised":
        fill(bx + bw / 2 - P * 0.35, by + bh * 0.2, P * 0.7, P * 0.7, EYE)
    elif face == "yawn":  # 하품하는 입
        fill(bx + bw / 2 - P * 0.5, by + bh * 0.12, P, P * 1.1, EYE)
    if getattr(c, "glasses", False):
        g, gw = max(1.0, P * 0.25), P * 1.9  # 테 두께, 알 크기 (눈이 움직여도 테는 얼굴에 고정)
        gy = by + bh * 0.55 - P * 0.35
        for cx in (3, 8):
            gx = bx + (cx - 2) * P * k - P * 0.45
            for x, y, w, h in ((gx, gy, gw, g), (gx, gy + gw - g, gw, g), (gx, gy, g, gw), (gx + gw - g, gy, g, gw)):
                fill(x, y, w, h, EYE)
        fill(bx + 1 * P * k + P * 1.45, gy + gw * 0.6, (5 * P * k) - P * 1.9, g, EYE)  # 코걸이
    hat = getattr(c, "hat", "none")
    if hat in HAT_PX:
        draw_hat(hat, bx + bw / 2, by + bh, P, P * k, c.dir)
    if s.get("prop"):
        draw_prop(c, s["prop"], bx, by, bw, bh)
    if getattr(c, "mark", None):  # 다른 에이전트 표식 (머리 위)
        px, color = c.mark
        mp = max(1.0, P * 0.5)
        mx, my = W / 2 - len(px[0]) * mp / 2, by + bh + P * 0.4
        for r, row in enumerate(px):
            for col, ch in enumerate(row):
                if ch == "X":
                    fill(mx + col * mp, my + (len(px) - 1 - r) * mp, mp, mp, color)
    NSGraphicsContext.restoreGraphicsState()
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
        if size.width > W:  # 긴 말(번역)은 창 밖으로 잘리지 않게 글자를 줄임
            attrs[NSFontAttributeName] = NSFont.boldSystemFontOfSize_(max(10, 2.5 * P) * W * 0.9 / size.width)
            size = ns.sizeWithAttributes_(attrs)
        lift = min(HAT_H.get(getattr(c, "hat", "none"), 0), 2) * P  # 모자 위로
        ns.drawAtPoint_withAttributes_((max(0, min(bx + bw + P * 0.5 - size.width / 2, W - size.width)), by + bh + P * 0.4 + lift + s["emoteRise"]), attrs)


# 모자: (가로 시작, 세로 시작, 너비, 높이, 색) - 가로는 몸통 가운데 기준 P*k, 세로는 머리 위 기준 P 단위
RED, RED_D, GOLD, BLUE, BLUE_D, PINK2, WHITE = "#D94F4F", "#A93A3A", "#F2C14E", "#5B7FC7", "#41609E", "#E26D8E", "#FFFFFF"
HAT_PX = {
    "cap": [(-2.6, -0.1, 5.2, 1.6, RED), (-0.4, 1.5, 0.8, 0.4, RED_D), (1.6, -0.1, 3.2, 0.5, RED_D)],
    "crown": [(-2.4, -0.1, 4.8, 1.0, GOLD), (-2.4, 0.9, 1.0, 0.9, GOLD), (-0.5, 0.9, 1.0, 0.9, GOLD), (1.4, 0.9, 1.0, 0.9, GOLD),
              (-0.35, 0.2, 0.7, 0.55, RED)],
    "party": [(-2.2 + 0.45 * i, -0.1 + 0.8 * i, 4.4 - 0.9 * i, 0.8, "#6B9BD8" if i % 2 == 0 else "#F2A0A8") for i in range(5)]
             + [(-0.5, 3.9, 1.0, 0.9, GOLD)],
    "beanie": [(-3.0, -0.1, 6.0, 1.6, BLUE), (-2.2, 1.5, 4.4, 0.5, BLUE), (-3.2, -0.1, 6.4, 0.6, BLUE_D), (-0.6, 2.0, 1.2, 0.9, WHITE)],
    "bow": [(1.2, -0.1, 1.2, 1.4, PINK2), (2.8, -0.1, 1.2, 1.4, PINK2), (2.3, 0.2, 0.6, 0.8, "#B94E6C")],
}
HAT_H = {k: max(y + h for _, y, _, h, _ in v) for k, v in HAT_PX.items()}


def draw_hat(hat, cx, top, P, uk, d):
    """d가 -1(왼쪽을 봄)이면 좌우를 뒤집어 챙·리본이 보는 쪽을 따라감."""
    for x, y, w, h, col in HAT_PX[hat]:
        left = cx + x * uk if d >= 0 else cx - (x + w) * uk
        fill(left, top + y * P, w * uk, h * P, rgb(col))


PAPER, INK, SCREEN, PROMPT = rgb("#FFFFFF"), rgb("#9AA3AD"), rgb("#2B2D31"), rgb("#4ADE80")


def oval(x, y, w, h, color, stroke=None, width=1.0):
    path = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x, y, w, h))
    if color:
        color.setFill()
        path.fill()
    if stroke:
        stroke.setStroke()
        path.setLineWidth_(width)
        path.stroke()


def draw_prop(c, prop, bx, by, bw, bh):
    """작업 종류별 소품 애니메이션. t는 초당 8씩 오르는 프레임 번호."""
    kind, t = prop
    P, W, top = c.P, c.W, by + bh
    if kind in ("read", "edit"):  # 몸 앞·손에 드는 소품
        if kind == "read":  # 펼친 책, 가끔 책장 넘김
            w, h, x, y = 5 * P, 2.4 * P, W / 2 - 2.5 * P, by + P * 0.2
            fill(x, y, w, h, PAPER)
            fill(W / 2 - P * 0.1, y, P * 0.2, h, INK)
            for i in range(3):
                fill(x + P * 0.4, y + h - P * (0.6 + i * 0.6), P * 1.6, P * 0.2, INK)
                fill(W / 2 + P * 0.4, y + h - P * (0.6 + i * 0.6), P * 1.6, P * 0.2, INK)
            flip = t % 24
            if flip < 6:  # 넘어가는 책장
                fill(W / 2 + P * 0.1, y + P * 0.2, P * 2.2 * (1 - flip / 6), h - P * 0.4, rgb("#EEF1F4"))
        else:  # 오른손 연필이 오르내리며 줄을 긋는 중
            bob = abs(math.sin(t * 0.9)) * P * 0.6
            x, y = bx + bw + P * 0.6, by + bh * 0.25 + P + bob
            fill(x, y, P * 0.8, P * 0.6, rgb("#3B3B3B"))         # 심
            fill(x, y + P * 0.6, P * 0.8, P * 2.4, rgb("#F2C14E"))  # 몸통
            fill(x, y + P * 3.0, P * 0.8, P * 0.5, rgb("#E58FA0"))  # 지우개
            fill(x - P * 1.6, by + P * 0.2, P * (0.4 + t % 12 / 12 * 2.2), P * 0.25, INK)  # 긋는 줄
        return
    if getattr(c, "mark", None):  # 머리 위는 다른 에이전트 표식 자리
        return
    x0, y0 = W / 2 + P * 0.4, top + P * 0.7
    if kind == "run":  # 작은 터미널: 프롬프트 + 깜빡이는 커서
        fill(x0, y0, 6 * P, 3.4 * P, SCREEN)
        fill(x0 + P * 0.5, y0 + P * 1.9, P * 0.5, P * 0.5, PROMPT)
        fill(x0 + P * 1.0, y0 + P * 1.6, P * 0.5, P * 0.5, PROMPT)
        fill(x0 + P * 0.5, y0 + P * 1.3, P * 0.5, P * 0.5, PROMPT)
        n = t % 16
        fill(x0 + P * 1.8, y0 + P * 1.5, P * 0.35 * min(n, 8), P * 0.4, rgb("#D1D5DB"))
        if t // 4 % 2:
            fill(x0 + P * (1.9 + 0.35 * min(n, 8)), y0 + P * 1.4, P * 0.5, P * 0.6, PROMPT)
    elif kind == "search":  # 돋보기가 빙글빙글
        cx, cy = x0 + P * 2.4 + math.cos(t * 0.45) * P, y0 + P * 2.2 + math.sin(t * 0.45) * P * 0.6
        path = NSBezierPath.bezierPath()
        path.moveToPoint_((cx + P * 0.8, cy - P * 0.8))
        path.lineToPoint_((cx + P * 1.8, cy - P * 1.8))
        rgb("#6B4F3A").setStroke()
        path.setLineWidth_(P * 0.5)
        path.stroke()
        oval(cx - P * 1.2, cy - P * 1.2, P * 2.4, P * 2.4, rgb("#BFE3F5", 0.85), rgb("#555B63"), P * 0.35)
    elif kind == "web":  # 도는 지구본
        r, cx, cy = P * 1.6, x0 + P * 2.2, y0 + P * 2
        oval(cx - r, cy - r, 2 * r, 2 * r, rgb("#3B82F6"))
        for k in range(2):
            lx = cx - r + ((t * P * 0.25 + k * r) % (2 * r))
            fill(lx - P * 0.4, cy - P * 0.6 + k * P * 0.8, P * 0.8, P * 0.7, rgb("#22C55E"))
        oval(cx - r, cy - r, 2 * r, 2 * r, None, rgb("#1E3A8A"), P * 0.25)
    elif kind == "plan":  # 체크리스트에 하나씩 체크
        fill(x0, y0, 4.4 * P, 4.6 * P, PAPER)
        fill(x0 + P * 1.4, y0 + P * 4.3, P * 1.6, P * 0.6, rgb("#8B6B4A"))
        done = t // 6 % 4
        for i in range(3):
            yy = y0 + P * (3.3 - i * 1.2)
            fill(x0 + P * 0.5, yy, P * 0.7, P * 0.7, rgb("#2E9E5B") if i < done else INK)
            fill(x0 + P * 1.6, yy + P * 0.2, P * 2.2, P * 0.3, INK)
    elif kind == "answer":  # 말풍선 안에 글이 써지는 중
        fill(x0, y0 + P * 0.6, 6 * P, 3 * P, PAPER)
        fill(x0 + P * 0.6, y0, P * 0.8, P * 0.7, PAPER)
        n = t % 20
        fill(x0 + P * 0.6, y0 + P * 2.6, P * 0.5 * min(n, 9), P * 0.35, INK)
        if n > 9:
            fill(x0 + P * 0.6, y0 + P * 1.5, P * 0.5 * (n - 9), P * 0.35, INK)
    else:  # 생각 중·서브에이전트: 생각 구름 점이 하나씩
        for i in range(t // 3 % 4):
            d = P * (0.6 + i * 0.35)
            oval(x0 + P * (0.4 + i * 1.3), y0 + P * i * 1.1, d, d, PAPER, INK, max(1.0, P * 0.15))


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
        self.work_kind = None  # 일하는 중이면 보여줄 동작 (activity.label_kind)
        self.cur_pose, self.drawn_key, self.drawn_pos = None, None, None  # 바뀐 게 없으면 다시 안 그리려고
        self.win = floating_window(NSMakeRect(self.x, self.y, self.W, self.H))
        self.view = CharView.alloc().initWithCritter_(self)
        self.win.setContentView_(self.view)
        self.win.orderFrontRegardless()

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, st):
        if st != getattr(self, "_state", None):
            self._state, self.state_start = st, time.time()

    @property
    def cx(self):
        return self.x + self.W / 2

    def set_scale(self, p):
        self.P, self.W, self.H = p, 16 * p, 13 * p
        self.drawn_key = None
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
        if self.state not in ("air", "jump", "happy", "flip"):
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
        if self.state in ("air", "jump", "flip"):
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
        # 배터리: 창 이동·다시 그리기는 화면에서 달라질 때만 (0.5pt 단위)
        pos = (round(self.x), round(self.y))
        if pos != self.drawn_pos:
            self.drawn_pos = pos
            self.win.setFrameOrigin_(pos)
        self.cur_pose = self.pose()
        key = tuple(round(v * 2) if isinstance(v, float) else v for v in self.cur_pose.values())
        if key != self.drawn_key:
            self.drawn_key = key
            self.view.setNeedsDisplay_(True)

    def pose(self):
        now = time.time()
        st = self.state
        w = st in ("walk", "fetch", "zoom")
        age = now - self.state_start  # 지금 동작을 시작한 지 몇 초
        ease = 0.5 - 0.5 * math.cos(min(1.0, age / 0.6) * math.pi)  # 0→1 부드럽게
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
        elif st == "zoom":
            tilt = -self.dir * 12 + math.sin(ph * 2) * 2
        elif w:
            tilt = -self.dir * 5 + math.sin(ph * 2) * 1.5
        elif st == "dance":
            tilt = math.sin(now * 6) * 10
        elif st == "trip":  # 앞으로 꽈당, 잠깐 엎어졌다가 일어남
            tilt = -self.dir * 75 * (ease if age < 1.2 else max(0.0, 1 - (age - 1.2) / 0.4))
        elif st == "sneeze":  # 들이마시며 뒤로, 에취! 하며 앞으로
            tilt = self.dir * 6 * ease if age < 0.7 else -self.dir * 12 * max(0.0, 1 - (age - 0.7) / 0.5)
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
        elif st in ("dance", "flip", "zoom"):
            face = "happy"
        elif st == "trip":
            face = "surprised" if age < 0.4 else "sad"
        elif st in ("stretch", "yawn"):
            face = "yawn" if st == "yawn" or 0.4 < age < 1.6 else "blink"
        elif st == "sneeze":
            face = "sleepy" if age < 0.7 else "surprised"
        elif st == "sit" and math.sin(now * 0.7) > 0.93:
            face = "blink"
        elif self.blink_at <= now < self.blink_at + 0.12:
            face = "blink"
        elif self.owner.night() and st in ("rest", "look"):
            face = "sleepy"
        else:
            face = "normal"
        wave = self.hover or st == "look"
        if typing:  # 타닥타닥
            armL, armR = abs(math.sin(now * 14)) * P * 0.6, abs(math.cos(now * 14)) * P * 0.6
        elif st == "dance":  # 양팔 번갈아 번쩍
            armL, armR = (P * 1.6, 0.0) if math.sin(now * 3) > 0 else (0.0, P * 1.6)
        elif st in ("stretch", "yawn"):  # 기지개
            up = P * (2.0 if st == "stretch" else 0.9) * (ease if age < 1.6 else max(0.0, 1 - (age - 1.6) / 0.4))
            armL = armR = up
        elif st == "sit":
            armL = armR = -P * 0.4
        elif st == "trip":
            armL = armR = P * 1.4 * ease
        elif dangle or st in ("happy", "jump"):
            armL = armR = P * 1.2
        else:
            armL = -step * P * 0.3 if w else 0.0
            armR = abs(math.sin(now * 9)) * P * 1.5 if wave else (step * P * 0.3 if w else 0.0)
        emote = self.emote_text if now < self.emote_until else self.owner.idle_emote(self)
        dance = math.sin(now * 6)
        stretch_up = 0.15 * (ease if age < 1.6 else max(0.0, 1 - (age - 1.6) / 0.4)) if st == "stretch" else 0.0
        pose = {
            "legA": max(0.0, step) ** 1.5 * P * 0.9 if w else (P * 0.6 * (0.5 + 0.5 * math.sin(now * 12)) if dangle else 0.0),
            "legB": max(0.0, -step) ** 1.5 * P * 0.9 if w else (P * 0.6 * (0.5 - 0.5 * math.sin(now * 12)) if dangle else 0.0),
            "bob": abs(step) * P * 0.3 if w else (P * 0.8 if dangle else (abs(math.sin(now * 14)) * P * 0.15 if typing else 0.0)),
            "squash": max(0.8, min(1.15, 1.0 + stretch - self.squash_v - (0.04 * breathe if not w else 0))),
            "armL": armL, "armR": armR,
            "lookX": self.sm_lx, "lookY": self.sm_ly, "tilt": self.sm_tilt,
            "shadow": not self.airborne() and st != "held",
            "face": face, "emote": emote,
            "emoteRise": ((now - self.emote_start) * 6 if now < self.emote_until else math.sin(now * 2) * 2) if emote else 0.0,
            "prop": (self.work_kind, int(now * 8)) if st == "work" and self.work_kind else None,
        }
        if st == "dance":  # 들썩들썩, 다리 번갈아
            pose.update(bob=abs(dance) * P * 0.6, legA=max(0.0, dance) * P * 0.6, legB=max(0.0, -dance) * P * 0.6)
        elif st == "sit":  # 몸을 낮춰 다리가 짧아 보이게
            pose.update(bob=-P * 1.1 * ease, squash=pose["squash"] * 0.97)
        elif st == "stretch":
            pose.update(squash=1.0 + stretch_up)
        elif st == "flip":  # 뛰어올라 한 바퀴
            pose.update(spin=-self.dir * 360 * min(1.0, age / 0.75))
        return pose
