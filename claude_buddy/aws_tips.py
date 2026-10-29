"""AWS 시험 팁 모듈.

이 파일을 지우면 Claude Buddy는 팁·질문하기 없이 순수 데스크톱 펫으로 동작합니다.
팁 출처: https://learningmate-lab.github.io/cloud-cbt/ (개념 정리 팁 + 문제 해설)
"""
import json
import os
import re
import ssl
import subprocess
import urllib.request
from pathlib import Path

import certifi

DATA_DIR = Path.home() / "Library" / "Application Support" / "Claude Buddy"
SRC_URL = "https://learningmate-lab.github.io/cloud-cbt/"
TIPS_FILE = DATA_DIR / "tips.json"
MODULES = {2: "글로벌 인프라", 3: "IAM", 4: "S3", 5: "EC2", 6: "데이터베이스", 7: "VPC"}
MODEL = "claude-haiku-5-5"  # 짧은 답이라 가장 저렴한 모델
KEYCHAIN = ("-s", "Claude Buddy", "-a", "anthropic-api-key")


def site_json(html, name):
    start = html.index(f"window.{name} = ") + len(f"window.{name} = ")
    return json.JSONDecoder().raw_decode(html[start:])[0]


def load_tips():
    if not TIPS_FILE.exists():
        html = urllib.request.urlopen(SRC_URL, timeout=20, context=ssl.create_default_context(cafile=certifi.where())).read().decode("utf-8")
        plain = lambda s: re.sub(r"\*\*|`", "", s).strip()
        tips = [{"module": m["module"], "head": f"모듈 {m['module']} · {s['title']}", "text": plain(s["tip"])}
                for m in site_json(html, "CLOUD_CONCEPTS") for s in m["sections"] if s.get("tip")]
        tips += [{"module": q["module"], "head": f"모듈 {q['module']} · {MODULES.get(q['module'], '')} 시험 포인트",
                  "text": plain(q["explain"])} for q in site_json(html, "CLOUD_QS") if q.get("explain")]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TIPS_FILE.write_text(json.dumps(tips, ensure_ascii=False, indent=1))
    tips = json.loads(TIPS_FILE.read_text())
    assert tips and all({"module", "head", "text"} <= t.keys() for t in tips), "tips.json 형식 오류: 파일을 지우고 다시 실행"
    return tips


JOSA = re.compile(r"(에서는|에서|으로|이란|이야|이에요|인가요|은|는|이|가|을|를|의|에|로|와|과|도|만|란|야|요|뭐야|뭔가요|뭐지)$")


def search_tips(tips, query, n=3):
    words = [JOSA.sub("", w.lower()) for w in re.findall(r"[A-Za-z0-9]+|[가-힣]+", query)]
    words = [w for w in words if len(w) >= 2 and w not in ("뭐야", "알려줘", "차이", "설명")] or words
    scored = []
    for t in tips:
        head, text = t["head"].lower(), t["text"].lower()
        s = sum((head.count(w) * 3 + text.count(w)) * len(w) for w in words)
        if s:
            scored.append((s, t))
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:n]]


def api_key():
    """환경변수 ANTHROPIC_API_KEY가 우선, 없으면 키체인에 저장한 키."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    r = subprocess.run(["security", "find-generic-password", *KEYCHAIN, "-w"], capture_output=True, text=True)
    return r.stdout.strip() or None


def save_api_key(key):
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,300}", key):  # 대화형 명령 줄에 그대로 들어가므로 키 형식만 허용
        return False
    # 키를 명령 인자 대신 표준 입력으로 넘겨 프로세스 목록에 남지 않게 함
    cmd = 'add-generic-password -U -s "Claude Buddy" -a anthropic-api-key -w "%s"\n' % key
    r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True)
    return r.returncode == 0 and api_key() == key


def delete_api_key():
    subprocess.run(["security", "delete-generic-password", *KEYCHAIN], capture_output=True)


def ask_claude(question, context_tips):
    """Claude에게 묻기. 인증 정보가 없거나 실패하면 None (로컬 검색 결과만 보여줌)."""
    try:
        import anthropic
        key = api_key()
        client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()  # 키가 없으면 ant auth login 정보
        notes = "\n".join(f"- [{t['head']}] {t['text']}" for t in context_tips)
        resp = client.messages.create(
            model=MODEL, max_tokens=400,  # 3문장 답에 충분, 토큰 절약
            thinking={"type": "disabled"}, output_config={"effort": "low"},
            system="당신은 AWS 자격증 공부를 돕는 데스크톱 펫입니다. 한국어로 3문장 이내, 시험 포인트 위주로 답하세요. "
                   "아래 학습 노트가 관련 있으면 그 내용을 우선 근거로 쓰세요.\n\n학습 노트:\n" + (notes or "(없음)"),
            messages=[{"role": "user", "content": question}],
        )
        if resp.stop_reason == "refusal":
            return None
        return "".join(b.text for b in resp.content if b.type == "text").strip() or None
    except Exception:  # noqa: BLE001 - 키 없음·네트워크 등 어떤 실패든 로컬 답으로 대체
        return None
