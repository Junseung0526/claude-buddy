"""화면 글자 번역. 코드 안 글자는 한국어 그대로 두고 t("한국어")로 감싸면 고른 언어로 바뀐다.
작업 라벨은 애니메이션 종류를 고르는 데 한국어로 쓰이므로 화면에 띄울 때만 localize()로 바꾼다."""

import re

from AppKit import NSLocale

LANGS = {"ko": "한국어", "en": "English", "ja": "日本語", "zh": "简体中文", "es": "Español"}
LLM_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Simplified Chinese", "es": "Spanish"}
ORDER = ("en", "ja", "zh", "es")
lang = "ko"

# 한국어 -> (영어, 일본어, 중국어, 스페인어). {이름}은 t(..., 이름=값)으로 채움
TR = {
    # 작업 라벨 조각
    "작업 완료": ("Done", "完了", "完成", "Listo"),
    "읽는 중": ("Reading", "読み込み中", "正在读取", "Leyendo"),
    "({n}줄부터)": ("(from line {n})", "({n}行目から)", "(从第 {n} 行)", "(desde la línea {n})"),
    "작성 중": ("Writing", "作成中", "正在写入", "Escribiendo"),
    "수정 중": ("Editing", "編集中", "正在编辑", "Editando"),
    "실행 중": ("Running", "実行中", "正在运行", "Ejecutando"),
    "코드 검색": ("Searching code", "コード検索", "搜索代码", "Buscando código"),
    "파일 찾는 중": ("Finding files", "ファイル検索中", "正在查找文件", "Buscando archivos"),
    "웹 검색": ("Web search", "ウェブ検索", "网页搜索", "Búsqueda web"),
    "웹 읽는 중": ("Reading web", "ウェブ閲覧中", "正在读取网页", "Leyendo web"),
    "페이지": ("page", "ページ", "页面", "página"),
    "서브에이전트": ("Subagent", "サブエージェント", "子代理", "Subagente"),
    "호출": ("call", "呼び出し", "调用", "llamada"),
    "스킬": ("Skill", "スキル", "技能", "Habilidad"),
    "계획 정리 중": ("Planning", "計画中", "正在规划", "Planificando"),
    "워크플로 실행 중": ("Running workflow", "ワークフロー実行中", "正在运行工作流", "Ejecutando flujo"),
    "도구": ("Tool", "ツール", "工具", "Herramienta"),
    "준비 중": ("Getting ready", "準備中", "准备中", "Preparando"),
    "새 요청 받음": ("New request", "新しいリクエスト", "收到新请求", "Nueva solicitud"),
    "생각 중": ("Thinking", "考え中", "思考中", "Pensando"),
    "답변 작성 중": ("Writing answer", "回答作成中", "正在撰写回答", "Escribiendo respuesta"),
    "질문에 답해 주세요": ("Please answer the question", "質問に答えてください", "请回答问题", "Responde la pregunta"),
    "권한 확인": ("Permission needed", "権限の確認", "需要授权", "Permiso necesario"),
    "명령 실행 중": ("Running command", "コマンド実行中", "正在执行命令", "Ejecutando comando"),
    "파일 수정 중": ("Editing files", "ファイル編集中", "正在编辑文件", "Editando archivos"),
    "검색 중": ("Searching", "検索中", "搜索中", "Buscando"),
    "도구 실행 중": ("Running tool", "ツール実行中", "正在运行工具", "Ejecutando herramienta"),
    "{n}단계": ("step {n}", "ステップ {n}", "第 {n} 步", "paso {n}"),
    "확인 필요": ("Needs you", "確認が必要", "需要确认", "Requiere atención"),
    "{n}초": ("{n}s", "{n}秒", "{n}秒", "{n} s"),
    "{n}분": ("{n}m", "{n}分", "{n}分钟", "{n} min"),
    # 캐릭터 머리 위
    "으아아": ("Whoa!", "うわあ", "哇啊", "¡Aaah!"),
    "취소!": ("Canceled!", "キャンセル!", "取消!", "¡Cancelado!"),
    "집중!": ("Focus!", "集中!", "专注!", "¡A concentrarse!"),
    "뿅!": ("Poof!", "ポン!", "噗!", "¡Puf!"),
    "통과!": ("Passed!", "合格!", "通过!", "¡Pasó!"),
    "테스트 실패..": ("Tests failed..", "テスト失敗..", "测试失败..", "Fallaron.."),
    "앗, 에러!": ("Oops, error!", "あっ、エラー!", "哎呀，出错!", "¡Uy, error!"),
    "새 버전!": ("New version!", "新バージョン!", "新版本!", "¡Nueva versión!"),
    "{v} 토큰!": ("{v} tokens!", "{v} トークン!", "{v} token!", "¡{v} tokens!"),
    "아야..": ("Ouch..", "いてて..", "哎哟..", "Ay.."),
    "완료!": ("Done!", "完了!", "完成!", "¡Listo!"),
    "어서와요!": ("Welcome back!", "おかえり!", "欢迎回来!", "¡Bienvenido!"),
    "또 던져줘!": ("Again!", "もう一回!", "再扔一次!", "¡Otra vez!"),
    "잡았다!": ("Got it!", "捕まえた!", "抓到了!", "¡La tengo!"),
    "확인 필요!": ("Check this!", "確認して!", "请确认!", "¡Revisa esto!"),
    "음…": ("Hmm…", "うーん…", "嗯…", "Mmm…"),
    "키 저장!": ("Key saved!", "キー保存!", "密钥已保存!", "¡Clave guardada!"),
    "저장 실패": ("Save failed", "保存失敗", "保存失败", "Error al guardar"),
    "키 삭제": ("Key deleted", "キー削除", "密钥已删除", "Clave borrada"),
    "따라갈게!": ("Following you!", "ついていくね!", "跟着你!", "¡Te sigo!"),
    "에취!": ("Achoo!", "くしゅん!", "阿嚏!", "¡Achís!"),
    # 말풍선·알림
    "지금: {label}": ("Now: {label}", "現在: {label}", "当前: {label}", "Ahora: {label}"),
    "Claude Code 확인 필요": ("Claude Code needs you", "Claude Code: 確認が必要", "Claude Code 需要确认", "Claude Code necesita tu atención"),
    "Claude Code 작업 완료": ("Claude Code finished", "Claude Code: 作業完了", "Claude Code 已完成", "Claude Code terminó"),
    "{n}분 걸린 작업을 마쳤어요": ("Finished a {n}-minute task", "{n}分かかった作業が終わりました", "已完成耗时 {n} 分钟的任务", "Terminó una tarea de {n} min"),
    "쉬는 시간": ("Break time", "休憩時間", "休息时间", "Hora del descanso"),
    "50분째 쉬지 않고 달리는 중이에요! 일어나서 기지개 한 번 켜고 물 한 잔 마셔요.": (
        "You've been going for 50 minutes straight! Stand up, stretch, and grab some water.",
        "50分ずっと休まず頑張っていますね！立ち上がって伸びをして、水を一杯飲みましょう。",
        "你已经连续忙了 50 分钟！站起来伸个懒腰，喝杯水吧。",
        "¡Llevas 50 minutos sin parar! Levántate, estírate y toma un poco de agua."),
    "늦은 밤": ("Late night", "深夜", "深夜", "Muy tarde"),
    "벌써 새벽 {h}시예요. 푹 자야 내일도 잘 풀려요. 오늘은 여기까지 할까요?": (
        "It's already {h} AM. A good night's sleep makes tomorrow go better. Call it a day?",
        "もう夜中の{h}時です。ぐっすり寝れば明日もうまくいきます。今日はここまでにしませんか？",
        "已经凌晨 {h} 点了。睡个好觉明天才会顺利。今天就到这里吧？",
        "Ya son las {h} de la madrugada. Dormir bien hace que mañana salga mejor. ¿Lo dejamos por hoy?"),
    "집중 시간 종료": ("Focus time over", "集中タイム終了", "专注时间结束", "Fin del tiempo de concentración"),
    "25분 집중을 마쳤어요. 5분 쉬고 물 한 잔 마신 뒤 다시 시작해요.": (
        "You finished 25 minutes of focus. Take 5, drink some water, then start again.",
        "25分の集中が終わりました。5分休んで水を飲んでから、また始めましょう。",
        "25 分钟专注完成。休息 5 分钟，喝杯水再开始吧。",
        "Terminaste 25 minutos de concentración. Descansa 5, bebe agua y vuelve a empezar."),
    "※ AI가 만든 답변이라 틀릴 수 있어요.": ("※ AI-generated answer; it may be wrong.", "※ AIが生成した回答のため、誤りを含む場合があります。", "※ 此回答由 AI 生成，可能有误。", "※ Respuesta generada por IA; puede contener errores."),
    "닫기": ("Close", "閉じる", "关闭", "Cerrar"),
    "궁금한 걸 입력하고 Enter": ("Ask anything and press Enter", "知りたいことを入力して Enter", "输入问题后按 Enter", "Escribe tu pregunta y pulsa Enter"),
    "질문": ("Question", "質問", "问题", "Pregunta"),
    "답을 받지 못했어요. claude·codex·agy CLI에 로그인하거나 설정에서 API 키를 넣어 주세요.": (
        "Couldn't get an answer. Sign in to the claude, codex or agy CLI, or add an API key in Settings.",
        "回答を取得できませんでした。claude・codex・agy CLI にログインするか、設定で API キーを入力してください。",
        "没有获得回答。请登录 claude、codex 或 agy CLI，或在设置中填写 API 密钥。",
        "No se obtuvo respuesta. Inicia sesión en la CLI de claude, codex o agy, o añade una clave API en Ajustes."),
    # 메뉴
    "{name} API 키를 붙여넣고 Enter ({hint})": ("Paste your {name} API key and press Enter ({hint})", "{name} API キーを貼り付けて Enter ({hint})",
                                         "粘贴 {name} API 密钥后按 Enter（{hint}）", "Pega tu clave API de {name} y pulsa Enter ({hint})"),
    "새 버전 {v} 받기…": ("Get new version {v}…", "新バージョン {v} を入手…", "获取新版本 {v}…", "Descargar versión {v}…"),
    "새 버전 확인": ("Check for updates", "アップデートを確認", "检查更新", "Buscar actualizaciones"),
    "로그인 시 자동 실행": ("Open at login", "ログイン時に起動", "登录时启动", "Abrir al iniciar sesión"),
    "Claude Buddy 업데이트": ("Claude Buddy update", "Claude Buddy アップデート", "Claude Buddy 更新", "Actualización de Claude Buddy"),
    "{v} 버전이 나왔어요. 메뉴에서 받을 수 있어요.": ("Version {v} is out. Get it from the menu.", "{v} が公開されました。メニューから入手できます。",
                                       "{v} 版本已发布，可在菜单中获取。", "Ya salió la versión {v}. Descárgala desde el menú."),
    "질문하기…": ("Ask…", "質問する…", "提问…", "Preguntar…"),
    "사용량 보기…": ("Usage…", "使用量を見る…", "查看用量…", "Ver uso…"),
    "간식 주기": ("Give a snack", "おやつをあげる", "喂零食", "Dar un bocadillo"),
    "공놀이": ("Play ball", "ボール遊び", "玩球", "Jugar a la pelota"),
    "커서 따라오기": ("Follow cursor", "カーソルについてくる", "跟随光标", "Seguir el cursor"),
    "집중 타이머 (25분)": ("Focus timer (25 min)", "集中タイマー (25分)", "专注计时 (25 分钟)", "Temporizador de enfoque (25 min)"),
    "집중 타이머 취소": ("Cancel focus timer", "集中タイマーをキャンセル", "取消专注计时", "Cancelar temporizador"),
    "30분 동안 쉬기": ("Nap for 30 min", "30分休む", "休息 30 分钟", "Descansar 30 min"),
    "질문 답변 모델": ("Answer model", "回答モデル", "回答模型", "Modelo de respuesta"),
    "{name} API 키 설정…": ("Set {name} API key…", "{name} API キーを設定…", "设置 {name} API 密钥…", "Configurar clave API de {name}…"),
    "{name} API 키 변경…": ("Change {name} API key…", "{name} API キーを変更…", "更改 {name} API 密钥…", "Cambiar clave API de {name}…"),
    "{name} API 키 삭제": ("Delete {name} API key", "{name} API キーを削除", "删除 {name} API 密钥", "Borrar clave API de {name}"),
    "설정": ("Settings", "設定", "设置", "Ajustes"),
    "크기": ("Size", "サイズ", "大小", "Tamaño"),
    "작게": ("Small", "小", "小", "Pequeño"),
    "보통": ("Normal", "普通", "中", "Normal"),
    "크게": ("Large", "大", "大", "Grande"),
    "걷는 속도": ("Walking speed", "歩く速さ", "行走速度", "Velocidad"),
    "느리게": ("Slow", "ゆっくり", "慢", "Lenta"),
    "빠르게": ("Fast", "速く", "快", "Rápida"),
    "소리": ("Sound", "サウンド", "声音", "Sonido"),
    "알림 (확인 필요·긴 작업 완료)": ("Notifications (needs you, long tasks done)", "通知 (確認が必要・長い作業の完了)",
                              "通知（需要确认、长任务完成）", "Notificaciones (atención, tareas largas)"),
    "창 위로 올라가기": ("Climb on windows", "ウィンドウに登る", "爬到窗口上", "Subir a las ventanas"),
    "에이전트 작업 보기": ("Show agent work", "エージェントの作業を表示", "显示代理工作", "Mostrar trabajo de agentes"),
    "언어": ("Language", "言語", "语言", "Idioma"),
    "시스템 설정 따르기": ("Use system language", "システムに合わせる", "跟随系统", "Usar idioma del sistema"),
    "캐릭터 보이기": ("Show character", "キャラクターを表示", "显示角色", "Mostrar personaje"),
    "캐릭터 숨기기": ("Hide character", "キャラクターを隠す", "隐藏角色", "Ocultar personaje"),
    "종료": ("Quit", "終了", "退出", "Salir"),
    # 사용량 창
    "Claude Code 사용량": ("Claude Code usage", "Claude Code 使用量", "Claude Code 用量", "Uso de Claude Code"),
    "{m}월 {d}일 · 출력 {v} 토큰": ("{m}/{d} · {v} output tokens", "{m}月{d}日 · 出力 {v} トークン", "{m}月{d}日 · 输出 {v} 个 token", "{d}/{m} · {v} tokens de salida"),
    "{m}/{d}": ("{m}/{d}", "{m}/{d}", "{m}/{d}", "{d}/{m}"),
    "오늘 출력": ("Output today", "今日の出力", "今日输出", "Salida hoy"),
    "오늘 입력": ("Input today", "今日の入力", "今日输入", "Entrada hoy"),
    "세션": ("Sessions", "セッション", "会话", "Sesiones"),
    "응답": ("Replies", "応答", "回复", "Respuestas"),
    "{n}개": ("{n}", "{n}件", "{n} 个", "{n}"),
    "{n}번": ("{n}", "{n}回", "{n} 次", "{n}"),
    "입력은 캐시 읽기 {v} 토큰을 뺀 값": ("Input excludes {v} cache-read tokens", "入力はキャッシュ読み取り {v} トークンを除いた値",
                                "输入不含 {v} 个缓存读取 token", "La entrada excluye {v} tokens leídos de caché"),
    "최근 7일 출력 토큰": ("Output tokens, last 7 days", "直近7日の出力トークン", "最近 7 天输出 token", "Tokens de salida, últimos 7 días"),
    "오늘": ("Today", "今日", "今天", "Hoy"),
    "오늘 프로젝트별 출력": ("Output by project today", "今日のプロジェクト別出力", "今日各项目输出", "Salida por proyecto hoy"),
    "오늘은 아직 기록이 없어요": ("Nothing recorded today yet", "今日はまだ記録がありません", "今天还没有记录", "Todavía no hay registros hoy"),
}


def system_lang():
    for code in NSLocale.preferredLanguages() or []:
        if code[:2] in LANGS:
            return code[:2]
    return "en"


def set_lang(code):
    """설정값("auto" 또는 언어 코드)으로 화면 언어를 정한다."""
    global lang
    lang = code if code in LANGS else system_lang()


def t(ko, **kw):
    """한국어 글자를 지금 언어로. 표에 없으면 그대로 (파일 이름 등)."""
    s = ko if lang == "ko" or ko not in TR else TR[ko][ORDER.index(lang)]
    return s.format(**kw) if kw else s


PIECES = ((re.compile(r"^(\d+)초$"), "{n}초"), (re.compile(r"^(\d+)분$"), "{n}분"), (re.compile(r"^(\d+)단계$"), "{n}단계"))


def localize(label):
    """작업 라벨("읽는 중 · app.py (120줄부터) · 20초")을 조각마다 번역."""
    if not label or lang == "ko":
        return label
    out = []
    for piece in label.split(" · "):
        for rx, key in PIECES:
            m = rx.match(piece)
            if m:
                piece = t(key, n=m[1])
                break
        else:
            piece = re.sub(r"\((\d+)줄부터\)", lambda m: t("({n}줄부터)", n=m[1]), t(piece))
        out.append(piece)
    return " · ".join(out)


def fmt(n):
    """큰 수를 언어에 맞게 짧게: 12.3만 / 12.3万 / 123.4K."""
    return re.sub(r"\.0(?=\D+$)", "", _fmt(n))  # 157.0K -> 157K


def _fmt(n):
    if lang in ("ko", "ja", "zh"):
        man, oku = {"ko": ("만", "억"), "ja": ("万", "億"), "zh": ("万", "亿")}[lang]
        return f"{n / 1e8:.1f}{oku}" if n >= 1e8 else f"{n / 1e4:,.0f}{man}" if n >= 1e7 else f"{n / 1e4:.1f}{man}" if n >= 1e4 else f"{n:,}"
    return f"{n / 1e9:.1f}B" if n >= 1e9 else f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}K" if n >= 1e3 else f"{n:,}"


if __name__ == "__main__":  # 셀프 체크: python -m claude_buddy.i18n
    for k, v in TR.items():
        assert len(v) == 4, k
        keys = set(re.findall(r"{(\w+)}", k))
        assert all(set(re.findall(r"{(\w+)}", x)) == keys for x in v), k  # 빈칸 이름이 언어마다 같은지
    set_lang("en")
    assert localize("읽는 중 · app.py (120줄부터) · 20초") == "Reading · app.py (from line 120) · 20s"
    assert localize("확인 필요 · 권한 확인") == "Needs you · Permission needed"
    assert t("{n}분 걸린 작업을 마쳤어요", n=3) == "Finished a 3-minute task" and fmt(12_300) == "12.3K" and fmt(157_000) == "157K" and fmt(3_000_000) == "3M"
    set_lang("ja")
    assert localize("도구 실행 중 · 3단계 · 2분") == "ツール実行中 · ステップ 3 · 2分" and fmt(21_300_000) == "2,130万"
    set_lang("ko")
    assert localize("읽는 중 · a.py") == "읽는 중 · a.py" and fmt(12_300) == "1.2만"
    print("ok")
