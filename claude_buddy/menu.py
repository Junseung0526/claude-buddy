"""메뉴 동작을 받는 Objective-C 대상(Ctl)과 메뉴 구성."""

import time

import objc
from AppKit import NSApp, NSMenuItem, NSWorkspace
from Foundation import NSObject, NSURL
from PyObjCTools import AppHelper

from . import i18n, llm, settings
from .config import RELEASES
from .i18n import localize, t
from .settings import login_item


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

    def setKey_(self, s):
        name, _, _, _, hint = llm.PROVIDERS[self.b.provider()]
        self.b.open_input(t("{name} API 키를 붙여넣고 Enter ({hint})", name=name, hint=hint), "keySubmit:", secure=True)

    def keySubmit_(self, s):
        self.b.submit_key(s.stringValue())

    def prefDeleteKey_(self, s):
        llm.delete_api_key(self.b.provider())
        self.b.main.emote(t("키 삭제"))
        self.later_refresh()

    # ----- 설정 창
    def later_refresh(self):
        AppHelper.callAfter(settings.refresh, self.b)  # 컨트롤의 동작이 끝난 뒤 창을 다시 그림

    def openSettings_(self, s):
        settings.open_settings(self.b)

    def prefToggle_(self, s):
        self.b.set_cfg(settings.TOGGLES[s.tag()], s.state() == 1)

    def prefScale_(self, s):
        self.b.set_cfg("scale", settings.SIZES[s.selectedSegment()])

    def prefSpeed_(self, s):
        self.b.set_cfg("speed", settings.SPEEDS[s.selectedSegment()])

    def prefLang_(self, s):
        i = s.indexOfSelectedItem()
        self.b.set_cfg("lang", "auto" if i == 0 else list(i18n.LANGS)[i - 1])
        self.later_refresh()

    def prefColor_(self, s):
        self.b.set_cfg("color", list(settings.COLORS)[s.indexOfSelectedItem()])

    def prefHat_(self, s):
        self.b.set_cfg("hat", list(settings.HATS)[s.indexOfSelectedItem()])

    def prefProvider_(self, s):
        self.b.set_cfg("ask_provider", list(llm.PROVIDERS)[s.indexOfSelectedItem()])
        self.later_refresh()

    def prefLogin_(self, s):
        self.toggleLogin_(s)
        self.later_refresh()

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

    def usage_(self, s):
        self.b.open_usage()

    def openRelease_(self, s):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(RELEASES))

    def toggleLogin_(self, s):
        svc = login_item()
        app = svc.mainAppService()
        if app.status() == 1:  # 켜져 있음
            app.unregisterAndReturnError_(None)
        else:
            app.registerAndReturnError_(None)
            if app.status() == 2:  # 사용자 승인이 필요하면 시스템 설정을 열어 줌
                svc.openSystemSettingsLoginItems()
        self.b.main.emote("OK!" if app.status() in (0, 1) else t("저장 실패"))

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
    if b.update_tag:
        m.addItem_(item(t("새 버전 {v} 받기…", v=b.update_tag), "openRelease:"))
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
    pref = item(t("설정…"), "openSettings:")
    pref.setKeyEquivalent_(",")
    m.addItem_(pref)
    if status:
        m.addItem_(item(t("캐릭터 보이기") if b.manual_hidden else t("캐릭터 숨기기"), "toggleHidden:"))
    m.addItem_(NSMenuItem.separatorItem())
    m.addItem_(item(t("종료"), "quit:"))
    return m
