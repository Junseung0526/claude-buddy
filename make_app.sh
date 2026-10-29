#!/bin/bash
# 한 번만 실행: 가상환경·의존성 설치 후 더블클릭용 "Claude 버디.app" 생성.
# 폴더를 옮겼다면 다시 실행하세요 (앱이 이 폴더 경로를 기억함).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/Claude 버디.app"

if [ ! -x "$DIR/.venv/bin/python" ]; then
  PY="$(command -v python3.14 || command -v python3)"
  "$PY" -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$DIR/requirements.txt"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# 아이콘: 캐릭터를 그려서 .icns로
TMP="$(mktemp -d)"
"$DIR/.venv/bin/python" "$DIR/buddy.py" --icon "$TMP/icon.png"
mkdir "$TMP/icon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$TMP/icon.png" --out "$TMP/icon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$TMP/icon.png" --out "$TMP/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$TMP/icon.iconset" -o "$APP/Contents/Resources/icon.icns"
rm -rf "$TMP"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Claude 버디</string>
  <key>CFBundleIdentifier</key><string>local.claude-buddy</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/launch" <<LAUNCH
#!/bin/bash
DIR="$DIR"
# 이미 떠 있으면 또 띄우지 않음
pgrep -f "\$DIR/buddy.py" >/dev/null && exit 0
exec "\$DIR/.venv/bin/python" "\$DIR/buddy.py" >>"\$HOME/Library/Logs/claude-buddy.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/launch"

echo "완료: $APP"
echo "더블클릭해서 실행하세요. Dock이나 응용 프로그램 폴더로 드래그해 둬도 됩니다."
