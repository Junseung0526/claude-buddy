"""질문하기 답변용 LLM 제공자(Claude·Gemini·GPT): 로그인된 CLI가 먼저, 없으면 API 키(macOS 키체인)."""
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.request

import certifi

# 제공자 -> (메뉴 이름, 모델, 환경변수, 키체인 계정, 키 입력 안내). 모두 짧은 답에 맞춘 저렴한 모델
PROVIDERS = {
    "claude": ("Claude", "claude-haiku-5-5", "ANTHROPIC_API_KEY", "anthropic-api-key", "sk-ant-…"),
    "gemini": ("Gemini", "gemini-flash-lite-latest", "GEMINI_API_KEY", "gemini-api-key", "AIza…"),
    "gpt": ("GPT", "gpt-5-mini", "OPENAI_API_KEY", "openai-api-key", "sk-…"),
}
MAX_TOKENS = 400  # 3문장 답에 충분, 토큰 절약
SERVICE = "Claude Buddy"
CLI_NAMES = {"claude": "claude", "gemini": "agy", "gpt": "codex"}
# 응용 프로그램으로 실행하면 PATH가 /usr/bin:/bin 뿐이라 CLI가 흔히 깔리는 곳을 더해서 찾음
CLI_PATH = os.pathsep.join([os.environ.get("PATH", ""), os.path.expanduser("~/.local/bin"),
                            "/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.npm-global/bin")])
WORK_DIR = os.path.expanduser("~/Library/Application Support/Claude Buddy")


def cli(provider):
    return shutil.which(CLI_NAMES[provider], path=CLI_PATH)


def ask_cli(provider, system, question):
    """로그인된 CLI로 한 번 묻는다 (도구·세션 기록 없이). 실패하면 None."""
    exe = cli(provider)
    if not exe:
        return None
    os.makedirs(WORK_DIR, exist_ok=True)
    env = {**os.environ, "PATH": CLI_PATH}
    prompt = f"{system}\n\n질문: {question}"  # codex·agy는 시스템 프롬프트 옵션이 없음
    out = None
    try:
        if provider == "claude":
            # 세션 기록을 남기지 않아 작업 표시에 잡히지 않음
            cmd = [exe, "-p", question, "--model", "haiku", "--system-prompt", system, "--tools", "",
                   "--no-session-persistence", "--strict-mcp-config", "--setting-sources", ""]
        elif provider == "gpt":
            # 팁은 웹에서 받은 글이라 읽기 전용 샌드박스(쓰기·네트워크 없음)에서만 돌림
            out = tempfile.NamedTemporaryFile(suffix=".txt", dir=WORK_DIR, delete=False).name
            cmd = [exe, "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                   "-c", 'model_reasoning_effort="low"', "-o", out, prompt]
        else:
            # 출력 모드는 명령 실행 권한을 묻지 못해 자동 거부, --sandbox로 터미널도 한 번 더 막음.
            # 기록은 Antigravity 로그 폴더 밖에 남겨 작업 표시에 잡히지 않음
            cmd = [exe, "-p", prompt, "--sandbox", "--effort", "low", "--disable-slash-commands",
                   "--log-file", os.path.join(WORK_DIR, "agy.log")]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=WORK_DIR, env=env,
                           stdin=subprocess.DEVNULL)
        text = (open(out).read() if out else r.stdout).replace("**", "")  # 말풍선은 마크다운을 못 그림
        return text.strip() if r.returncode == 0 and text.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if out and os.path.exists(out):
            os.remove(out)


def api_key(provider):
    """환경변수가 우선, 없으면 키체인에 저장한 키."""
    _, _, env, account, _ = PROVIDERS[provider]
    if os.environ.get(env):
        return os.environ[env]
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"], capture_output=True, text=True)
    return r.stdout.strip() or None


def save_api_key(provider, key):
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,300}", key):  # 대화형 명령 줄에 그대로 들어가므로 키 형식만 허용
        return False
    # 키를 명령 인자 대신 표준 입력으로 넘겨 프로세스 목록에 남지 않게 함
    cmd = 'add-generic-password -U -s "%s" -a %s -w "%s"\n' % (SERVICE, PROVIDERS[provider][3], key)
    r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True)
    return r.returncode == 0 and api_key(provider) == key


def delete_api_key(provider):
    subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", PROVIDERS[provider][3]], capture_output=True)


def post_json(url, body, headers):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read())


def ask(provider, system, question):
    """답변 글자, 실패하면 None (부르는 쪽이 로컬 검색 결과로 대신함). CLI가 먼저, 안 되면 API 키."""
    text = ask_cli(provider, system, question)
    if text:
        return text
    try:
        model, key = PROVIDERS[provider][1], api_key(provider)
        if provider == "claude":
            import anthropic
            if not key:
                return None
            client = anthropic.Anthropic(api_key=key)
            resp = client.messages.create(
                model=model, max_tokens=MAX_TOKENS, thinking={"type": "disabled"}, output_config={"effort": "low"},
                system=system, messages=[{"role": "user", "content": question}])
            if resp.stop_reason == "refusal":
                return None
            text = "".join(b.text for b in resp.content if b.type == "text")
        elif not key:
            return None
        elif provider == "gemini":
            data = post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": question}]}],
                "generationConfig": {"maxOutputTokens": MAX_TOKENS},
            }, {"x-goog-api-key": key})
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        else:
            data = post_json("https://api.openai.com/v1/chat/completions", {
                "model": model, "reasoning_effort": "minimal",
                "max_completion_tokens": MAX_TOKENS * 2,  # 추론 토큰도 여기서 빠짐
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
            }, {"Authorization": f"Bearer {key}"})
            text = data["choices"][0]["message"]["content"] or ""
        return text.strip() or None
    except Exception:  # noqa: BLE001 - 키 없음·네트워크·형식 변경 등 어떤 실패든 로컬 답으로 대체
        return None
