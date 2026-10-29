"""전체 조율: 매 프레임 처리, 행동 결정, 말풍선, 질문하기."""

import datetime
import random
import threading
import time

from AppKit import (
    NSApp, NSAppearance, NSAppearanceNameAqua, NSBackingStoreBuffered, NSColor, NSEvent, NSFloatingWindowLevel, NSFont, NSMakeRect,
    NSMenu, NSSecureTextField, NSStatusBar, NSTextField, NSWindow, NSWindowStyleMaskClosable, NSWindowStyleMaskTitled,
)
from Foundation import NSRunLoop, NSRunLoopCommonModes, NSTimer
from PyObjCTools import AppHelper
from Quartz import (
    CGEventSourceSecondsSinceLastEventType, kCGAnyInputEventType, kCGEventSourceStateHIDSystemState,
)

from . import i18n, llm, usage
from .i18n import localize, t
from .activity import Activity, label_kind
from .config import BUBBLE_W, MAX_MINIS, SHOW_SEC, save_settings
from .critter import Critter
from .gfx import AGENT_LOOKS, GRAY, HEART, KeyWindow, MINI_COLORS, ORANGE, ORANGE_HEX, floating_window, label, notify, play, rgb
from .icon import icon_image
from .menu import Ctl
from .toy import TOY, Toy
from .widgets import BubbleView, Chip, UsageView, pill
from .world import World


SYSTEM = "You are a desktop pet and helper living on the user's screen. Answer in {language} in at most 3 short, accurate sentences."


class Buddy:
    def __init__(self, cfg):
        self.cfg = cfg
        i18n.set_lang(cfg["lang"])
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
        self.ask_win, self.menu_open = None, False
        self.manual_hidden, self.hidden, self.fullscreen = False, False, False
        self.hover_since, self.hover_petted = 0.0, False
        now = time.time()
        self.last = now
        self.next_slow = 0.0
        self.activity = Activity()
        self.alerted = False  # 이번 확인 필요를 이미 알렸는지
        self.active_since, self.was_idle, self.stretch_told, self.night_told = now, False, False, None
        self.status = NSStatusBar.systemStatusBar().statusItemWithLength_(-1)
        self.status.button().setImage_(icon_image(18))
        menu = NSMenu.alloc().init()
        menu.setDelegate_(self.ctl)
        self.status.setMenu_(menu)
        self.timer, self.fps = None, 0
        self.set_rate(60)

    def set_rate(self, fps):
        """배터리: 움직일 때만 60fps, 가만히 있으면 20fps, 숨었으면 2fps."""
        if fps == self.fps:
            return
        if self.timer:
            self.timer.invalidate()
        self.fps = fps
        self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1 / fps, self.ctl, "tick:", None, True)
        self.timer.setTolerance_(0.2 / fps)  # macOS가 깨우기를 묶어서 처리하도록
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def lively(self):
        """빠른 움직임(걷기·점프·들기·장난감)이 있어 60fps가 필요한지."""
        calm = ("rest", "sleep", "work", "focus", "look", "sit")
        crits = [self.main, *self.minis.values()]
        return bool(self.grab or self.toy) or any(
            k.state not in calm or k.airborne() or k.squash_v > 0 or getattr(k, "done_at", None) for k in crits)

    # ----- 설정
    def set_cfg(self, key, val):
        self.cfg[key] = val
        save_settings(self.cfg)
        if key == "scale":
            self.main.set_scale(val)
            for c in self.minis.values():
                c.set_scale(max(3, round(val * (0.7 if c.mark else 0.55))))
        if key == "lang":
            i18n.set_lang(val)
            self.chip.text = None  # 칩을 새 언어로 다시 그리게
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
        if c.state == "dance":
            return ("♪" if int(now * 2) % 2 else "♫", ORANGE)
        if c.state == "sneeze" and now - c.state_start > 0.7:
            return (t("에취!"), GRAY)
        if c.state == "trip" and 0.4 < now - c.state_start < 1.4:
            return (t("아야.."), GRAY)
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
                self.close_bubble()
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
                self.pet(c)
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
        c.emote(t("으아아") if fast else "~")
        if fast:
            c.feel("surprised", 1.2)

    def pet(self, c):
        c.hop()
        c.emote(HEART, rgb("#E0456B"))
        play(self.cfg, "Tink")

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
            c.emote(t("취소!"), GRAY)
        else:
            self.close_bubble()
            self.focus_until = time.time() + 25 * 60
            c.emote(t("집중!"))

    def snooze(self):
        self.close_bubble()
        self.main.state, self.main.state_until = "sleep", time.time() + 30 * 60

    # ----- 미니 (서브에이전트)
    def add_mini(self, aid):
        i = len(self.minis)
        look = AGENT_LOOKS.get(self.activity.sub(aid).get("kind"))
        c = Critter(self, self.world, max(3, round(self.cfg["scale"] * (0.7 if look else 0.55))),
                    self.main.x + random.uniform(-40, 40), look[0] if look else MINI_COLORS[i % len(MINI_COLORS)], mini=True)
        c.mark = (look[1], rgb(look[2])) if look else None
        c.y = self.main.y
        c.hop(380, "happy", 0.8)
        c.emote(t("뿅!"))
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
        s = self.activity.sub(aid)
        if s:
            self.show({"head": s["desc"] if s.get("kind") else t("서브에이전트") + f" · {s['desc']}",
                       "text": t("지금: {label}", label=localize(s["tail"].label or t("준비 중")))}, anchor=c)

    # ----- 매 프레임
    def tick(self):
        now = time.time()
        dt = min(now - self.last, 0.05)
        self.last = now
        self.world.refresh(now, 0.4 if self.fps == 60 else 2.0)  # 배터리: 가만히 있을 땐 창 위치를 드물게
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
            self.set_rate(2)
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
            c.emote(t("아야.."), GRAY)
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
            s = self.activity.sub(aid)
            chip = self.mini_chips.get(aid)
            if chip:
                chip.set(s["tail"].text(now) if s and not mc.done_at else None)
                mc.work_kind = label_kind(s["tail"].label) if s and not mc.done_at else None
                chip.place(mc.cx, mc.y + mc.H, mc.state != "held")

        if self.toy:
            if self.toy.carried:
                self.toy.x, self.toy.y = c.cx - TOY / 2, c.y + c.H * 0.62
            self.toy.physics(dt)
            self.toy.render()

        if self.bubble and now > self.bubble_until:
            self.close_bubble()
        self.chip.place(c.cx, c.y + c.H, not self.bubble and c.state != "held")
        c.work_kind = label_kind(self.activity.main.label) if c.state == "work" and self.activity.main else None
        self.set_rate(60 if self.lively() else 20)

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
            wait = self.activity.waiting(now)
            if wait and not self.alerted:
                play(self.cfg, "Funk")
                notify(self.cfg, t("Claude Code 확인 필요"), localize(wait))
            self.alerted = bool(wait)
            if self.activity.finished_after >= 60:  # 1분 넘게 걸린 작업만 알림
                notify(self.cfg, t("Claude Code 작업 완료"), t("{n}분 걸린 작업을 마쳤어요", n=int(self.activity.finished_after // 60)))
                self.activity.finished_after = 0.0
            elif self.activity.finished_after:
                self.activity.finished_after = 0.0
            subs = self.activity.active_subs()
            for aid, s in subs.items():
                if aid not in self.minis and not s["finished"] and len(self.minis) < MAX_MINIS:
                    self.add_mini(aid)
                elif aid in self.minis and s["finished"] and self.minis[aid].done_at is None:
                    mc = self.minis[aid]
                    mc.done_at = now
                    mc.hop(420, "happy", 1.5)
                    mc.emote(t("완료!"), rgb("#2E7D32"), 2)
                    play(self.cfg, "Glass")
            for aid in [a for a, mc in self.minis.items() if a not in subs]:
                self.remove_mini(aid)

        idle = CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateHIDSystemState, kCGAnyInputEventType)
        if idle > 300:
            self.active_since = now
            if not self.was_idle and c.state in ("walk", "rest", "look", "sit") and not self.focus_until:
                self.was_idle = True
                c.state, c.state_until = "sleep", now + 3600
        elif self.was_idle and idle < 2:
            self.was_idle = False
            c.state, c.state_until = "rest", now + 1
            c.feel("surprised", 0.8)
            c.hop(380, "happy", 1.0)
            c.emote(t("어서와요!"))
        if now - self.active_since > 50 * 60 and not self.bubble and not self.focus_until:
            self.active_since = now
            self.show({"head": t("쉬는 시간"), "text": t("50분째 쉬지 않고 달리는 중이에요! 일어나서 기지개 한 번 켜고 물 한 잔 마셔요.")})
        today = datetime.date.today()
        if self.night() and self.night_told != today and not self.bubble:
            self.night_told = today
            self.show({"head": t("늦은 밤"), "text": t("벌써 새벽 {h}시예요. 푹 자야 내일도 잘 풀려요. 오늘은 여기까지 할까요?", h=datetime.datetime.now().hour)})

    def brain(self, now, dt, m):
        c = self.main
        if c.state in ("held", "air", "jump", "flip") or (c.state == "happy" and (now < c.state_until or c.airborne())):
            return
        if c.state == "happy":
            c.state = "rest"
        speed = self.cfg["speed"]
        toy = self.toy
        if self.bubble or self.menu_open or self.asking():  # 메뉴·질문창이 캐릭터를 따라가지 않게 멈춤
            if c.state in ("walk", "fetch", "zoom", "dance"):
                c.state = "rest"
            return
        if toy and toy.carried:  # 공 물고 커서한테 돌아오기
            ty = self.world.ground(m.x, m.y)
            if c.chase(m.x, ty, speed * 2, dt, 30):
                toy.carried, toy.waiting = False, True
                toy.vy, toy.vx = 250.0, c.dir * 60
                c.emote(t("또 던져줘!"))
                c.state = "look"
            return
        if toy and toy.settled():
            if c.chase(toy.cx, toy.y, speed * 2.4, dt, 8):
                if toy.kind == "snack":
                    toy.close()
                    self.toy = None
                    c.hop()
                    c.emote(HEART, rgb("#E0456B"), 1.8)
                    play(self.cfg, "Bottle")
                else:
                    toy.carried = True
                    c.emote(t("잡았다!"))
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
                self.show({"head": t("집중 시간 종료"), "text": t("25분 집중을 마쳤어요. 5분 쉬고 물 한 잔 마신 뒤 다시 시작해요.")})
            return
        if self.cfg["activity"] and self.activity.waiting(now) and c.state != "sleep":
            c.state, c.state_until = "look", now + 2  # 손 흔들며 부르기
            c.emote(t("확인 필요!"), rgb("#D9534F"), 1.5)
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
        elif c.state == "zoom":  # 우다다
            c.walk(dt, speed * 3.2)
        if now > c.state_until:  # 다음 행동 고르기
            if c.state == "sleep":
                c.emote("!")
            night = self.night()
            moves = {"walk": 5, "rest": 2, "look": 2, "sleep": 3 if night else 1, "climb": 2 if self.cfg["windows"] else 0,
                     "sit": 1.5, "dance": 0.3 if night else 1, "stretch": 1, "yawn": 1.5 if night else 0.3,
                     "zoom": 0.1 if night else 0.7, "flip": 0.1 if night else 0.5, "trip": 0.3, "sneeze": 0.3}
            nxt = random.choices(list(moves), list(moves.values()))[0]
            if nxt == "climb":
                plat = self.world.platform_above(c.cx, c.y)
                if plat:
                    c.jump_to(random.uniform(plat[0] + 30, plat[1] - 30), plat[2])
                    return
                nxt = "walk"
            if nxt == "flip":
                c.hop(620, "flip", 2.0)
                play(self.cfg, "Pop")
                return
            c.state = nxt
            c.state_until = now + {"walk": random.uniform(5, 14), "rest": random.uniform(2, 4),
                                   "look": random.uniform(2, 3), "sleep": random.uniform(8, 15),
                                   "sit": random.uniform(4, 9), "dance": random.uniform(3, 5), "stretch": 2.0, "yawn": 2.2,
                                   "zoom": random.uniform(1.5, 3), "trip": 1.8, "sneeze": 1.4}[nxt]
            if nxt in ("walk", "zoom") and random.random() < 0.4:
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
    def close_bubble(self):
        if self.bubble:
            self.bubble.orderOut_(None)
            self.bubble = None

    def show(self, msg, anchor=None, extra=None):
        """msg={"head", "text"} 말풍선. extra=[(버튼 글자, 함수)]는 닫기 앞에 붙는 버튼."""
        self.close_bubble()
        c = anchor or self.main
        play(self.cfg, "Pop")
        if c is self.main and not c.airborne() and c.state in ("walk", "rest", "look", "work", "fetch"):
            c.hop(300, "happy", 0.6)
        c.emote("!")
        pad, inner = 16, BUBBLE_W - 32
        head = label(msg["head"], 12, ORANGE, bold=True, width=inner)
        body = label(msg["text"], 14, rgb("#222222"), width=inner)
        hh, th = head.fittingSize().height, body.fittingSize().height
        buttons = extra or []
        pills = [pill(txt, fn, ORANGE, NSColor.whiteColor()) for txt, fn in buttons]
        pills.append(pill(t("닫기"), self.close_bubble, rgb("#F1EDE8"), rgb("#666666")))
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

    # ----- 사용량 창
    def open_usage(self):
        if not getattr(self, "usage_win", None):
            w, h = 460, 452
            win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, w, h), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable, NSBackingStoreBuffered, False)
            win.setReleasedWhenClosed_(False)
            win.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameAqua))
            win.setLevel_(NSFloatingWindowLevel)
            win.setContentView_(UsageView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h)))
            win.center()
            self.usage_win = win
        self.usage_win.setTitle_(t("Claude Code 사용량"))
        self.usage_win.contentView().setData_(usage.summary())  # 열 때마다 새로 셈 (새 줄만 읽어서 빠름)
        self.usage_win.makeKeyAndOrderFront_(None)
        try:
            NSApp().activate()
        except AttributeError:
            NSApp().activateIgnoringOtherApps_(True)

    # ----- 물어보기
    def provider(self):
        p = self.cfg.get("ask_provider")
        return p if p in llm.PROVIDERS else "claude"

    def asking(self):
        return bool(self.ask_win and self.ask_win.isVisible())

    def open_ask(self):
        self.open_input(t("궁금한 걸 입력하고 Enter"), "askSubmit:")
        self.main.emote("?")

    def open_input(self, placeholder, action, secure=False):
        self.close_bubble()
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
        field = (NSSecureTextField if secure else NSTextField).alloc().initWithFrame_(NSMakeRect(14, 22, w - 28, 26))
        field.setPlaceholderString_(placeholder)
        field.setFont_(NSFont.systemFontOfSize_(13))
        field.setTextColor_(rgb("#222222"))  # 다크 모드에서 흰 글자로 안 보이던 문제
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        field.setFocusRingType_(1)  # 포커스 테두리 없음
        field.setTarget_(self.ctl)
        field.setAction_(action)
        bv.addSubview_(field)
        win.makeKeyAndOrderFront_(None)
        win.makeFirstResponder_(field)
        try:
            NSApp().activate()
        except AttributeError:
            NSApp().activateIgnoringOtherApps_(True)
        self.ask_win = win
        c.state, c.state_until = "look", time.time() + 5

    def submit_key(self, key):
        if self.ask_win:
            self.ask_win.orderOut_(None)
            self.ask_win = None
        if key.strip():
            ok = llm.save_api_key(self.provider(), key)
            self.main.emote(t("키 저장!") if ok else t("저장 실패"), GRAY if not ok else ORANGE)

    def submit_ask(self, q):
        if self.ask_win:
            self.ask_win.orderOut_(None)
            self.ask_win = None
        q = q.strip()
        if not q:
            return
        c = self.main
        c.emote(t("음…"), GRAY, 30)
        c.feel("work", 30)

        def work():
            answer = llm.ask(self.provider(), SYSTEM.format(language=i18n.LLM_NAMES[i18n.lang]), q)
            AppHelper.callAfter(self.answer, q, answer)

        threading.Thread(target=work, daemon=True).start()

    def answer(self, q, answer):
        c = self.main
        c.emote_until = c.face_until = 0
        if answer:
            self.show({"head": f"{llm.PROVIDERS[self.provider()][0]} · {q[:40]}", "text": answer + "\n\n" + t("※ AI가 만든 답변이라 틀릴 수 있어요.")})
        else:
            c.feel("sad", 1.5)
            self.show({"head": t("질문") + f" · {q[:40]}", "text": t("답을 받지 못했어요. claude·codex·agy CLI에 로그인하거나 설정에서 API 키를 넣어 주세요.")})
