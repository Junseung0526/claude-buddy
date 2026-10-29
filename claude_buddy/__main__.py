"""실행 진입점: python -m claude_buddy"""

import argparse

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from .app import Buddy
from .config import aws_tips, load_settings
from .icon import write_icon


def main():
    ap = argparse.ArgumentParser(description="AWS 시험 팁 + Claude Code 작업 상황을 보여주는 Claude 데스크톱 펫")
    ap.add_argument("--icon", help="아이콘 PNG만 만들고 종료 (build.sh용)")
    args = ap.parse_args()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # Dock 아이콘 없이
    if args.icon:
        write_icon(args.icon)
        return
    buddy = Buddy(aws_tips.load_tips() if aws_tips else [], load_settings())  # noqa: F841 (앱이 도는 동안 참조 유지)
    app.run()


if __name__ == "__main__":
    main()
