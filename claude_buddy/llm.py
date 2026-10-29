"""질문하기 답변용 LLM 제공자(Claude·Gemini·GPT)와 API 키(macOS 키체인) 관리."""
import json
import os
import re
import ssl
import subprocess
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
    """답변 글자, 실패하면 None (부르는 쪽이 로컬 검색 결과로 대신함)."""
    try:
        model, key = PROVIDERS[provider][1], api_key(provider)
        if provider == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()  # 키가 없으면 ant auth login 정보
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
