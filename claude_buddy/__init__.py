"""화면을 돌아다니며 Claude Code 작업 상황을 보여주는 Claude 캐릭터 데스크톱 펫 (macOS).
claude_buddy/aws_tips.py가 있으면 AWS 시험 팁·질문하기 기능이 켜지고, 지우면 순수 펫으로 동작함.

설치: GitHub Releases에서 Claude Buddy.app을 받거나, ./build.sh로 직접 빌드
직접 실행: .venv/bin/python buddy.py  또는  .venv/bin/python -m claude_buddy

상호작용
  클릭 다음 팁 · 더블클릭 쓰다듬기 · 드래그 들기/던지기 · 커서 올리기 손 흔들기
  우클릭(또는 메뉴바 아이콘) 질문하기 / 간식 / 공놀이 / 따라오기 / 집중 타이머 / 재우기 / 설정
  Claude Code가 일하면 머리 위에 지금 하는 작업이 뜨고, 서브에이전트마다 작은 캐릭터가 나와서 같이 일함
"""
