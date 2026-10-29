#!/bin/bash
# 독립 실행형 "Claude Buddy.app"을 빌드하고 배포용 zip을 만든다 (Python 설치 없이 실행 가능).
# 결과: dist/Claude Buddy.app, dist/Claude-Buddy-macOS-<아키텍처>.zip
set -euo pipefail
cd "$(dirname "$0")"
NAME="Claude Buddy"
VERSION="${VERSION:-1.0.0}"

if [ ! -x .venv/bin/python ]; then
  "$(command -v python3.14 || command -v python3)" -m venv .venv
fi
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt pyinstaller

# 아이콘: 캐릭터를 그려서 .icns로
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
.venv/bin/python buddy.py --icon "$TMP/icon.png"
mkdir "$TMP/icon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$TMP/icon.png" --out "$TMP/icon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$TMP/icon.png" --out "$TMP/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$TMP/icon.iconset" -o "$TMP/icon.icns"

rm -rf build dist
.venv/bin/pyinstaller --noconfirm --clean --windowed --log-level WARN \
  --name "$NAME" --icon "$TMP/icon.icns" --osx-bundle-identifier local.claude-buddy \
  --specpath "$TMP" buddy.py

APP="dist/$NAME.app"
PLIST="$APP/Contents/Info.plist"
plutil -replace LSUIElement -bool true "$PLIST"  # Dock 아이콘 없이 메뉴바에만
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
codesign --force --deep --sign - "$APP"  # Info.plist를 고쳤으니 ad-hoc 서명 다시

ZIP="dist/Claude-Buddy-macOS-$(uname -m).zip"
ditto -c -k --keepParent "$APP" "$ZIP"
echo "완료: $APP"
echo "배포용: $ZIP"
