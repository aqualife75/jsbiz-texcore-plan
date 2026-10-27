# texcore-plan — 자료 폴더 하나로 텍스코어 사업신청서 만들기

창업(탐색)팀 자료 폴더(IR 덱·사업계획서·특허·사진)를 넣고 한 문장만 말하면, 6개 AI 에이전트가 텍스코어(공공기술기반 시장연계 창업탐색 지원사업 · 실험실창업탐색팀) **공식 사업신청서 hwp 양식**을 심사위원 눈높이로 채워 주는 Claude Code 플러그인입니다. 결론 박스 → 증거 그림 → 짧은 문단 구조로 쓰고, 자료에 없는 숫자는 만들지 않고 `[기입 필요]`·`[확보 필요]`로 남깁니다.

👉 **[교육생용 사용법 가이드 보기](https://aqualife75.github.io/jsbiz-texcore-plan/)**

## 무엇이 나오나요

| 산출물 | 설명 |
|---|---|
| `{팀명}_사업신청서.hwp` · `.hwpx` | 공식 양식 그대로(표지 포함 10쪽 이내). 한글에서 바로 열어 고칠 수 있습니다 |
| `{팀명}_사업신청서.pdf` | 쪽수·그림 배치 확인용 |
| `심사대비_패키지.md` | 셀프 채점표(실제 평가표 5항목 100점 + 해외형 P/F) · 예상 의견서 · 예상 질의 15개와 답 뼈대 · **제출 전 확보 필요 목록** · 제출 체크리스트 · 5분 발표영상 대본 뼈대 |
| `팀_확인사항.md` | 팀만 아는 값(인적사항·특허번호·인터뷰 수 등)이 비어 있는 자리의 1:1 위치표. **EL이 마지막으로 읽고 채우는 문서** |
| `qa_png/` | 쪽별 PNG. 한글을 열지 않고도 그림·표·결론 박스 배치를 눈으로 확인 |

## 설치

```
/plugin marketplace add aqualife75/jsbiz-texcore-plan
/plugin install texcore-plan@jsbiz-texcore-plan
```

설치 후 Claude Code를 새 세션으로 다시 시작하세요. `/texcore-plan`이 자동완성되면 성공입니다.

## Codex 사용자

Claude Code 대신 OpenAI Codex를 쓰면 플러그인 설치 없이 **작업 폴더 ZIP**을 씁니다. [Releases](https://github.com/aqualife75/jsbiz-texcore-plan/releases/latest)에서 `정석biz-TexCore-Plan-v<버전>.zip`을 받아 압축을 풀고, `정석biz-텍스코어-프로젝트` 폴더를 Codex에서 연 뒤 `자료넣는곳`에 팀 자료를 넣고 "우리 팀 텍스코어 신청서 만들어줘"라고 말하면 됩니다. 같은 하네스(스킬·역할 6개·스크립트)가 `.agents/skills/texcore-plan`과 `.codex/agents`에 들어 있고, 결과는 `결과물/결과보기.html`에서 봅니다. 자세한 내용은 ZIP 안의 `사용설명서.html`. 저장소에서 직접 만들려면 `python scripts/build_codex_package.py`(→ `dist/`).

## Gemini·ChatGPT 웹 사용자

Claude Code도 Codex도 없으면 [프롬프트 북](https://aqualife75.github.io/jsbiz-texcore-plan/web.html)(원본 `web/텍스코어_신청서_프롬프트북.md`)을 씁니다. 같은 6단계를 붙여넣기 프롬프트 9단계로 풀어 두었고, 결과는 텍스트로 받아 한글 양식에 직접 옮깁니다. 자동 주입과 숫자 추적 검사는 없으므로 8단계 숫자 대조표로 대신합니다. 페이지는 `python scripts/build_web_prompts.py`로 다시 만듭니다.

## 실행

```
/texcore-plan "C:\Users\나\Desktop\우리팀_자료" --type 해외
```

"이 폴더 자료로 텍스코어 신청서 만들어줘"처럼 말로 부탁해도 됩니다.
주요 옵션: `--team 팀명` · `--type 해외|국내` · `--out 출력폴더` · `--resume` · `--from N` · `--accept-risk` · `--yes`

## 최소 요구사항

| 항목 | 필수 | 용도 |
|---|---|---|
| Claude Code | ● | 실행 |
| Python 3.10+ | ● | 추출·검증·숫자 추적·도식 렌더 |
| `pip install -r requirements.txt` (python-pptx pymupdf pillow olefile python-docx openpyxl jsonschema lxml pywin32) | ● | 의존 패키지 |
| Chrome 또는 Edge | ● | 증거 도식 12종 렌더(헤드리스) · 근거 캡처 |
| **Windows + 한글(HWP)** | ● (5단계) | 공식 hwp 양식에 본문·표·그림을 직접 주입(COM). 맥은 도식 렌더까지 하고 주입 사양(`08_fill_spec.json`)을 남깁니다 |
| Pretendard 폰트 | ○ | 도식 글꼴. 없으면 맑은 고딕으로 대체 |

## 6단계 요약

| 단계 | 에이전트 | 하는 일 | 산출 |
|---|---|---|---|
| 1. 자료 판독 | `tp-intake` | hwp·pdf·pptx·이미지 추출 → 양식 13슬롯 사실 팩 · 이미지 카탈로그 · **팀 질문지** | `02_fact_pack.json` · `02_team_questions.md` |
| 2. 본문 작성 | `tp-writer` | 칸별 목차(결론 한 문장·배점·쪽 예산) → 결론 박스→소제목→증거 그림→짧은 문단 | `03_outline.json` · `04_draft_v1.json` |
| 3. 모의심사 | `tp-panel` | 숫자 검산 + VC·TLO·도메인·I-Corps 인스트럭터·비전문가 5인이 실제 평가표로 채점 | `05_review/summary.json` |
| 4. 근거 조사 | `tp-researcher` | 약한 칸만 KIPRIS 특허·시장 통계·인증 요건·경쟁사 공식 사양 조사 후 개정 | `06_evidence/` · `07_draft_v2.json` |
| 5. 도식 + 주입 | `tp-designer` | 증거 도식 12종 렌더 → 한글 COM 주입 → 쪽별 PNG 검수(10쪽) | `08_figures/` · `09_build/` |
| 6. 심사 대비 | `tp-finalizer` | 셀프 채점·예상 질의·확보 목록·제출 체크리스트·팀 확인사항 | `10_final/` |

실제 팀 자료 기준 2시간 안팎. 진행 중 세 번 확인합니다 — ① 팀 질문지를 보낼지 ② 칸별 목차 표 ③ 남은 critical 승인.

## 꼭 알아두세요

- **초안입니다.** 자격(EL 재지원 가능 여부, 예비창업자 요건 등)·인적사항·특허번호·실적은 팀이 직접 확인해 채워야 합니다. `팀_확인사항.md`가 그 목록입니다.
- **없는 숫자는 만들지 않습니다.** 본문·그림의 모든 숫자는 사실 팩(팀 자료) 또는 증거 원장(공식 출처)과 대조(`trace`)되며, 근거 없는 숫자가 있으면 다음 단계로 넘어가지 않습니다.
- **모의심사 기준은 공개판에서는 일반화된 기준**입니다. 실제 심사 데이터는 포함하지 않습니다.
- 저장소의 예시 팀 「진동지기」는 교육용 가상 팀이며 모든 숫자는 예시입니다.
- 공고 연도가 바뀌면 `assets/template/`의 원본 양식과 `references/evaluation_guide.md`를 새 공고로 갱신해야 합니다(현재 2026년 공고 기준).

## 개발

```
pip install -r requirements.txt
pytest -q
python scripts/install_local.py --target "<.claude 폴더>"   # 로컬 .claude 설치본 동기화
```

만든이: 정석Biz · 이동건 · 유튜브 [@정석Biz](https://www.youtube.com/@정석Biz) · [GitHub](https://github.com/aqualife75/jsbiz-texcore-plan) · 자매 플러그인 [seed-ir](https://github.com/aqualife75/jsbiz-seed-ir)(Seed IR Deck)
