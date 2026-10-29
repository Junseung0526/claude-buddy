"""메뉴 동작을 받는 Objective-C 대상(Ctl)과 메뉴 구성."""

import time

import objc
from AppKit import NSApp, NSMenu, NSMenuItem
from Foundation import NSObject

from . import i18n, llm
from .i18n import localize, t


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

    def ask_(self, s):
        self.b.open_ask()

    def setProvider_(self, s):
        self.b.set_cfg("ask_provider", list(llm.PROVIDERS)[s.tag()])

    def setKey_(self, s):
        name, _, _, _, hint = llm.PROVIDERS[self.b.provider()]
        self.b.open_input(t("{name} API 키를 붙여넣고 Enter ({hint})", name=name, hint=hint), "keySubmit:", secure=True)

    def keySubmit_(self, s):
        self.b.submit_key(s.stringValue())

    def deleteKey_(self, s):
        llm.delete_api_key(self.b.provider())
        self.b.main.emote(t("키 삭제"))

    def askSubmit_(self, s):
        self.b.submit_ask(s.stringValue())

    def snack_(self, s):
        self.b.spawn_toy("snack")

    def ball_(self, s):
        self.b.spawn_toy("ball")

    def follow_(self, s):
        self.b.follow = not self.b.follow
        self.b.main.emote(t("따라갈게!") if self.b.follow else "OK")

    def focus_(self, s):
        self.b.toggle_focus()

    def snooze_(self, s):
        self.b.snooze()

    def toggleHidden_(self, s):
        self.b.manual_hidden = not self.b.manual_hidden

    def setScale_(self, s):
        self.b.set_cfg("scale", s.tag())

    def setSpeed_(self, s):
        self.b.set_cfg("speed", s.tag())

    def usage_(self, s):
        self.b.open_usage()

    def setLang_(self, s):
        self.b.set_cfg("lang", "auto" if s.tag() == 0 else list(i18n.LANGS)[s.tag() - 1])

    def toggleNotify_(self, s):
        self.b.set_cfg("notify", not self.b.cfg["notify"])

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
        head = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Claude Code: {localize(label_now)}", None, "")
        head.setEnabled_(False)
        m.addItem_(head)
        for aid, c in b.minis.items():
            s = b.activity.sub(aid)
            if s:
                it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"   └ {s['desc']}: {localize(s['tail'].label or '준비 중')}", None, "")
                it.setEnabled_(False)
                m.addItem_(it)
        m.addItem_(NSMenuItem.separatorItem())
    m.addItem_(item(t("질문하기…"), "ask:"))
    m.addItem_(item(t("사용량 보기…"), "usage:"))
    m.addItem_(NSMenuItem.separatorItem())
    m.addItem_(item(t("간식 주기"), "snack:"))
    m.addItem_(item(t("공놀이"), "ball:"))
    m.addItem_(item(t("커서 따라오기"), "follow:", on=b.follow))
    m.addItem_(item(t("집중 타이머 취소") if b.focus_until else t("집중 타이머 (25분)"), "focus:"))
    m.addItem_(item(t("30분 동안 쉬기"), "snooze:"))
    m.addItem_(NSMenuItem.separatorItem())
    c = b.cfg
    # 질문하기 답변 모델과 그 API 키 (CLI가 없을 때만 씀, 키체인에 저장)
    prov = b.provider()
    name = llm.PROVIDERS[prov][0]
    has_key = llm.api_key(prov) is not None
    ask_items = [sub(t("질문 답변 모델"), [item(f"{v[0]} ({v[1]})", "setProvider:", i, k == prov)
                                   for i, (k, v) in enumerate(llm.PROVIDERS.items())]),
                item(t("{name} API 키 변경…" if has_key else "{name} API 키 설정…", name=name), "setKey:")]
    ask_items += [item(t("{name} API 키 삭제", name=name), "deleteKey:")] if has_key else []
    m.addItem_(sub(t("설정"), ask_items + [
        sub(t("크기"), [item(n, "setScale:", v, c["scale"] == v) for n, v in ((t("작게"), 4), (t("보통"), 6), (t("크게"), 8))]),
        sub(t("걷는 속도"), [item(n, "setSpeed:", v, c["speed"] == v) for n, v in ((t("느리게"), 35), (t("보통"), 55), (t("빠르게"), 85))]),
        item(t("소리"), "toggleSound:", on=c["sound"]),
        item(t("알림 (확인 필요·긴 작업 완료)"), "toggleNotify:", on=c["notify"]),
        item(t("창 위로 올라가기"), "toggleWindows:", on=c["windows"]),
        item(t("에이전트 작업 보기"), "toggleActivity:", on=c["activity"]),
        sub(t("언어") + ("" if i18n.lang == "en" else " / Language"), [item(t("시스템 설정 따르기"), "setLang:", 0, c["lang"] == "auto")]
            + [item(name, "setLang:", i + 1, c["lang"] == k) for i, (k, name) in enumerate(i18n.LANGS.items())]),
    ]))
    if status:
        m.addItem_(item(t("캐릭터 보이기") if b.manual_hidden else t("캐릭터 숨기기"), "toggleHidden:"))
    m.addItem_(NSMenuItem.separatorItem())
    m.addItem_(item(t("종료"), "quit:"))
    return m
