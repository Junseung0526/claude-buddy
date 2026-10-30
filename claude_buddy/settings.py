"""설정 창 (⌘,): 일반·모습·동작·질문하기·시스템."""

import functools
import sys

import objc
from AppKit import (
    NSAppearance, NSAppearanceNameAqua, NSBackingStoreBuffered, NSButton, NSFont, NSGridCell, NSGridView, NSMakeRect, NSPopUpButton,
    NSSegmentedControl, NSSwitch, NSTextField, NSView, NSWindow, NSWindowStyleMaskClosable, NSWindowStyleMaskTitled,
)

from . import i18n, llm
from .i18n import t

@functools.cache
def login_item():
    """로그인 시 자동 실행 (SMAppService). 소스로 실행 중이면 None (등록할 앱 번들이 없음)."""
    if not getattr(sys, "frozen", False):
        return None
    ns = {}
    objc.loadBundle("ServiceManagement", ns, bundle_path="/System/Library/Frameworks/ServiceManagement.framework")
    return objc.lookUpClass("SMAppService")


SIZES, SPEEDS = (4, 6, 8), (35, 55, 85)
TOGGLES = ("sound", "notify", "windows", "activity", "updates", "glasses")
COLORS = {"#D97757": "주황", "#E58FA8": "분홍", "#5DBB9A": "민트", "#6B9BD8": "파랑", "#9B7BD4": "보라", "#E5B94E": "노랑", "#8E8E93": "회색"}
HATS = {"none": "없음", "cap": "야구모자", "crown": "왕관", "party": "파티 모자", "beanie": "비니", "bow": "리본"}


def _label(text, bold=False):
    f = NSTextField.labelWithString_(text)
    if bold:
        f.setFont_(NSFont.boldSystemFontOfSize_(13))
    return f


def _popup(ctl, sel, titles, index):
    p = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 200, 26), False)
    p.addItemsWithTitles_(titles)
    p.selectItemAtIndex_(index)
    p.setTarget_(ctl)
    p.setAction_(sel)
    return p


def _segments(ctl, sel, titles, index):
    s = NSSegmentedControl.segmentedControlWithLabels_trackingMode_target_action_(titles, 0, ctl, sel)
    s.setSelectedSegment_(index)
    return s


def _switch(ctl, sel, on, tag=0):
    s = NSSwitch.alloc().init()
    s.setState_(1 if on else 0)
    s.setTag_(tag)
    s.setTarget_(ctl)
    s.setAction_(sel)
    return s


def _button(ctl, sel, title):
    return NSButton.buttonWithTitle_target_action_(title, ctl, sel)


def build(b):
    """현재 설정으로 창 내용(NSGridView)을 만든다. 언어가 바뀌면 통째로 다시 만든다."""
    c, ctl = b.cfg, b.ctl
    toggle = lambda key: _switch(ctl, "prefToggle:", c[key], TOGGLES.index(key))
    langs = list(i18n.LANGS)
    prov = b.provider()
    keyed = llm.api_key(prov) is not None
    key_row = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 220, 26))
    btn = _button(ctl, "setKey:", t("변경…" if keyed else "설정…"))
    btn.setFrameOrigin_((0, 0))
    key_row.addSubview_(btn)
    if keyed:
        d = _button(ctl, "prefDeleteKey:", t("삭제"))
        d.setFrameOrigin_((btn.frame().size.width + 6, 0))
        key_row.addSubview_(d)
    rows = [
        (t("일반"), None),
        (t("언어"), _popup(ctl, "prefLang:", [t("시스템 설정 따르기")] + list(i18n.LANGS.values()),
                         0 if c["lang"] == "auto" else langs.index(c["lang"]) + 1)),
        (t("크기"), _segments(ctl, "prefScale:", [t("작게"), t("보통"), t("크게")], SIZES.index(c["scale"]) if c["scale"] in SIZES else 1)),
        (t("걷는 속도"), _segments(ctl, "prefSpeed:", [t("느리게"), t("보통"), t("빠르게")], SPEEDS.index(c["speed"]) if c["speed"] in SPEEDS else 1)),
        (t("모습"), None),
        (t("색상"), _popup(ctl, "prefColor:", [t(v) for v in COLORS.values()], list(COLORS).index(c["color"]) if c["color"] in COLORS else 0)),
        (t("모자"), _popup(ctl, "prefHat:", [t(v) for v in HATS.values()], list(HATS).index(c["hat"]) if c["hat"] in HATS else 0)),
        (t("안경"), toggle("glasses")),
        (t("동작"), None),
        (t("소리"), toggle("sound")),
        (t("알림 (확인 필요·긴 작업 완료)"), toggle("notify")),
        (t("창 위로 올라가기"), toggle("windows")),
        (t("에이전트 작업 보기"), toggle("activity")),
        (t("질문하기"), None),
        (t("질문 답변 모델"), _popup(ctl, "prefProvider:", [f"{v[0]} ({v[1]})" for v in llm.PROVIDERS.values()], list(llm.PROVIDERS).index(prov))),
        (t("{name} API 키", name=llm.PROVIDERS[prov][0]), key_row),
        (t("시스템"), None),
        (t("새 버전 확인"), toggle("updates")),
    ]
    if login_item():
        rows.append((t("로그인 시 자동 실행"), _switch(ctl, "prefLogin:", login_item().mainAppService().status() == 1)))
    empty = NSGridCell.emptyContentView()
    grid = NSGridView.gridViewWithViews_([[_label(name, bold=view is None), view or empty] for name, view in rows])
    grid.setRowSpacing_(10)
    grid.setColumnSpacing_(14)
    grid.columnAtIndex_(0).setXPlacement_(3)  # 이름은 오른쪽 정렬 (NSGridCellPlacementTrailing)
    for i, (_, view) in enumerate(rows):
        if view is None:  # 구역 제목은 두 칸을 합치고 위에 여백
            grid.mergeCellsInHorizontalRange_verticalRange_((0, 2), (i, 1))
            grid.cellAtColumnIndex_rowIndex_(0, i).setXPlacement_(1)  # 왼쪽 정렬
            if i:
                grid.rowAtIndex_(i).setTopPadding_(10)
    return grid


def open_settings(b):
    win = getattr(b, "settings_win", None)
    if not win:
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 420, 600), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable, NSBackingStoreBuffered, False)
        win.setReleasedWhenClosed_(False)
        win.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameAqua))
        b.settings_win = win
    refresh(b)
    if not win.isVisible():
        win.center()
    win.makeKeyAndOrderFront_(None)
    b.activate()


def refresh(b):
    """열려 있는 설정 창을 지금 설정·언어로 다시 그림."""
    win = getattr(b, "settings_win", None)
    if not win:
        return
    grid = build(b)
    pad = 24
    size = grid.fittingSize()
    holder = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, size.width + pad * 2, size.height + pad * 2))
    grid.setFrame_(NSMakeRect(pad, pad, size.width, size.height))
    holder.addSubview_(grid)
    top = win.frame().origin.y + win.frame().size.height
    win.setContentSize_(holder.frame().size)
    win.setContentView_(holder)
    if win.isVisible():  # 크기가 바뀌어도 위쪽 모서리는 그대로
        f = win.frame()
        win.setFrameOrigin_((f.origin.x, top - f.size.height))
    win.setTitle_(t("설정"))
