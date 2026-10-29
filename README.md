# Claude 버디

화면을 돌아다니며 AWS 자격증 시험 팁을 알려주고, Claude Code가 지금 무슨 작업을 하는지 보여주는 macOS 데스크톱 펫.

- 팁: [cloud-cbt](https://learningmate-lab.github.io/cloud-cbt/)의 개념 정리 팁·문제 해설 (첫 실행 때 받아옴)
- Claude Code 작업 표시: 머리 위에 현재 작업, 서브에이전트마다 작은 캐릭터가 나와서 같이 일함
- 클릭 다음 팁 · 더블클릭 쓰다듬기 · 드래그 들기/던지기 · 우클릭(또는 메뉴바 ✳︎) 물어보기/간식/공놀이/따라오기/집중 타이머/설정
- 창 위로 올라가 걷기, 여러 모니터, 전체화면 앱에서 자동 숨김

## 설치·실행

macOS + Python 3.10 이상.

```bash
./make_app.sh
```

만들어진 `Claude 버디.app`을 더블클릭. 직접 실행하려면 `.venv/bin/python buddy.py`.

물어보기에서 Claude 답변을 받으려면 `ANTHROPIC_API_KEY`를 설정하거나 `ant auth login`. 없으면 팁 검색 결과로 답합니다.
