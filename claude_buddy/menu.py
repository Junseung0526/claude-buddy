"""메뉴 동작을 받는 Objective-C 대상(Ctl)과 메뉴 구성."""

import time

import objc
from AppKit import NSApp, NSMenu, NSMenuItem
from Foundation import NSObject

from .config import aws_tips


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
        build_menu(self.b, menu, status=True)

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


def build_menu(b, m, status=False):
    """캐릭터 우클릭 메뉴와 메뉴바 메뉴를 채운다 (status=True면 메뉴바용 항목 추가)."""
    def item(title, sel, tag=0, on=False, target=None):
        it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
        it.setTarget_(target or b.ctl)
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

    label_now = b.activity.label(time.time()) if b.cfg["activity"] else None
    if label_now:
        head = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Claude Code: {label_now}", None, "")
        head.setEnabled_(False)
        m.addItem_(head)
        for aid, c in b.minis.items():
            s = b.activity.subs.get(aid)
            if s:
                it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"   └ {s['desc']}: {s['tail'].label or '준비 중'}", None, "")
                it.setEnabled_(False)
                m.addItem_(it)
        m.addItem_(NSMenuItem.separatorItem())
    if aws_tips:
        m.addItem_(item("다음 팁", "nextTip:"))
        m.addItem_(item("질문하기…", "ask:"))
        m.addItem_(sub("모듈별 팁", [item("전체", "setModule:", 0, b.module is None)]
                       + [item(f"모듈 {k} · {n}", "setModule:", k, b.module == k) for k, n in aws_tips.MODULES.items()]))
        m.addItem_(NSMenuItem.separatorItem())
    m.addItem_(item("간식 주기", "snack:"))
    m.addItem_(item("공놀이", "ball:"))
    m.addItem_(item("커서 따라오기", "follow:", on=b.follow))
    m.addItem_(item("집중 타이머 취소" if b.focus_until else "집중 타이머 (25분)", "focus:"))
    m.addItem_(item("30분 동안 쉬기", "snooze:"))
    m.addItem_(NSMenuItem.separatorItem())
    c = b.cfg
    tip_gap = [sub("팁 간격", [item(n, "setInterval:", v, c["interval"] == v) for n, v in
                           (("1분", 60), ("3분", 180), ("5분", 300), ("10분", 600), ("30분", 1800))])] if aws_tips else []
    m.addItem_(sub("설정", tip_gap + [
        sub("크기", [item(n, "setScale:", v, c["scale"] == v) for n, v in (("작게", 4), ("보통", 6), ("크게", 8))]),
        sub("걷는 속도", [item(n, "setSpeed:", v, c["speed"] == v) for n, v in (("느리게", 35), ("보통", 55), ("빠르게", 85))]),
        item("소리", "toggleSound:", on=c["sound"]),
        item("창 위로 올라가기", "toggleWindows:", on=c["windows"]),
        item("Claude Code 작업 보기", "toggleActivity:", on=c["activity"]),
    ]))
    if status:
        m.addItem_(item("캐릭터 보이기" if b.manual_hidden else "캐릭터 숨기기", "toggleHidden:"))
    m.addItem_(NSMenuItem.separatorItem())
    m.addItem_(item("종료", "quit:"))
    return m
