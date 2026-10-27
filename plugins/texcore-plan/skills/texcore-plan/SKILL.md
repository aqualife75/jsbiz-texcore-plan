---
name: texcore-plan
description: >-
  창업(탐색)팀 자료 폴더(hwp/hwpx·pdf·docx·pptx·xlsx·이미지)를 넣으면 텍스코어(TeX-Corps, 공공기술기반 시장연계 창업탐색 지원사업·실험실창업탐색팀) 공식 사업신청서 hwp 양식을 심사위원 매력도 기준으로 자동 작성하는 멀티 에이전트 하네스 오케스트레이터. 6단계 — ①자료 판독(사실 팩·이미지 카탈로그·팀 질문지) ②칸별 목차(결론 한 문장)·본문(결론 박스→증거 그림→짧은 문단, 쉬운 언어) ③실제 평가표(아이템20·핵심기술15·사업화25·팀20·참여의지20) 5인 모의심사 ④근거 조사(KIPRIS 특허·시장 통계·인증 요건)·개정 ⑤증거 도식 11종 생성 + 한글 COM으로 양식 주입·10쪽 검수 ⑥심사 대비 패키지(셀프 점수·예상 질의·확보 목록·제출 체크리스트·팀 확인사항). 정석Biz 예창패 작성법·충북대 미니 텍스코어 파트 II·III 강의안 기준. 모든 숫자는 사실 팩/증거 원장으로 추적되고 없는 숫자는 [기입 필요]/[확보 필요]로 남긴다. 트리거: "/texcore-plan <폴더>", "텍스코어 신청서 만들어줘", "실험실창업탐색팀 사업신청서 작성", "이 폴더 자료로 텍스코어 사업신청서", "텍스코어 양식 채워줘". 비트리거: IR 덱(→seed-ir), 예창패·초창패 등 다른 정부지원사업 사업계획서 첨삭(→biz-mentor), 텍스코어 팀 고객개발 진단(→texcore-customer-dev-review), 멘토링 보고서(→mentoring-report*).
---

# /texcore-plan — 텍스코어 사업신청서 멀티 에이전트 하네스 (오케스트레이터)

너는 **오케스트레이터**다. 본문·숫자·그림을 직접 쓰지 않는다. 순서·게이트·재개·사용자 확인만 맡고, 판단은 6개 서브에이전트에, 규칙은 `scripts/harness.py`에 맡긴다.

## 준비
- `SKILL_DIR` = 이 SKILL.md가 있는 폴더의 절대경로. `PY` = 파이썬 실행 명령(Windows 데스크탑: `py -3 -X utf8` 또는 `"C:/Users/<me>/AppData/Local/Programs/Python/Python312/python.exe" -X utf8`; 맥: `python3`). 처음 한 번 `PY -c "import pptx, fitz, PIL, olefile, docx, openpyxl, jsonschema"`로 확인, 실패 시 `pip install python-pptx pymupdf pillow olefile python-docx openpyxl jsonschema` 안내. 한글 주입(5단계)은 Windows + 한글(HWP) + pywin32가 필요하다.
- `HARNESS` = `PY "SKILL_DIR/scripts/harness.py"`.
- 에이전트 이름: 사용 가능한 목록에서 `tp-intake`·`tp-writer`·`tp-panel`·`tp-researcher`·`tp-designer`·`tp-finalizer`로 **끝나는** 이름을 고른다.
- 모든 Agent 프롬프트는 반드시 이 세 줄로 시작: `WS=<워크스페이스 절대경로>` / `SKILL_DIR=<SKILL_DIR>` / `PY=<PY>`. 그 뒤 `MODE=`·`PERSONA=`·`SLOT=`.
- 원칙: 실제 팀 자료와 산출물은 사용자 로컬 WS에만 둔다. 외부로 보내지 않는다.

## 인자
`/texcore-plan <입력폴더> [--team 팀명] [--type 해외|국내] [--out 출력폴더] [--resume] [--from N] [--accept-risk] [--yes]`
- 자연어로 왔으면 폴더 경로·교육유형을 뽑는다. 폴더가 없으면 한 번만 묻는다. 교육유형이 자료에도 없으면 1단계 뒤에 한 번 묻는다(해외교육형이 기본, 영문 요약·미국 시장 P/F가 추가된다).
- `--yes`: 체크포인트 3개(팀 질문지 발송 대기·목차 확인·critical 잔존 승인)를 건너뛴다. `--resume`: state.json의 done 단계 건너뜀(WS는 입력폴더 상위의 `*_{팀}_TexcorePlan` 최신 폴더). `--from N`: N단계부터.

## 실행 순서

### 0 INTAKE
1. `HARNESS init "<입력폴더>" [--team] [--type] [--out]` → 출력의 `WS=` 줄에서 워크스페이스 확보.
2. `HARNESS extract --ws "WS"` → 파일 수·글자 수·이미지 수·경고를 사용자에게 3줄 보고. 미지원·실패 파일은 "한글에서 PDF로 저장 후 폴더에 추가하고 `--resume`" 안내하고 계속.

### 1 FACTS
- Agent(tp-intake): `WS=…\nSKILL_DIR=…\nPY=…\n자료 전량 판독 후 02_fact_pack.json·image_catalog.json·02_team_questions.md 작성.`
- `HARNESS gate 2 --ws "WS"` 실패 시 사유를 tp-intake에 그대로 전달해 1회 재시도. 그래도 실패면 중단·보고.
- 보고: 13슬롯 상태 · 교육유형 · 증거 가치 high 이미지 수 · gaps 상위 5.
- **체크포인트 1(팀 질문지)**: `02_team_questions.md`의 high 질문을 사용자에게 보여주고 선택을 받는다 — "팀에게 보내고 답을 기다린다(답을 폴더에 넣고 `--resume`)" / "지금 아는 것으로 계속(빈칸은 `[기입 필요]`로 남고 최종 `팀_확인사항.md`에 모인다)". `--yes`면 계속.

### 2 WRITE
- Agent(tp-writer) `MODE=outline` → 반환된 표(칸·배점·질문·결론·증거·상태)를 **사용자에게 그대로 보여주고 확인**(체크포인트 2, `--yes`면 생략). outline에 `edu_type_assumed: true`면 교육유형을 함께 묻는다. 수정 요청이 있으면 그 문장을 붙여 outline 재호출.
- Agent(tp-writer) `MODE=draft` → `HARNESS gate 3 --ws "WS"`(실패 시 사유 전달 1회 재시도).
- 보고: 섹션 수 · 그림/표 수 · `[기입 필요]` 건수 · lint 경고 수.

### 3 REVIEW
- **한 메시지에서 6개 동시 호출**: Agent(tp-panel) × `PERSONA=numbers|vc|tlo|domain|icorps|layman`.
- 6개 완료 후 Agent(tp-panel) `PERSONA=chair`. `HARNESS gate 4 --ws "WS"`.
- 보고: 항목별 점수(중앙값)·합계·5인 평균 · P/F · 섹션 O/△/X 한 줄 · critical 건수 · 가독성 판정.

### 4 RESEARCH
- 조사 슬롯 집합: `05_review/summary.json`의 section_check △/X 섹션 → 슬롯(form_map 표) + critical/major issue의 section_id → 슬롯 + fact_pack.gaps의 slot_ids. **팀 내부 슬롯(I-1, I-2b, II-2b, III-1, III-3, IV, EN)은 제외**하고 I-2c·I-2d·II-1·II-2a·III-2 중심(최대 6개). II-2a(KIPRIS)는 특허가 하나라도 있으면 항상 포함.
- **한 메시지에서 동시 호출**: Agent(tp-researcher) `MODE=gap SLOT=<id>` × 슬롯 수.
- 완료 후 Agent(tp-researcher) `MODE=merge`.
- `HARNESS gate 5 --ws "WS"`:
  - 통과 → 5로.
  - `critical 미해결` 사유만 남았으면 목록을 보여주고 **사용자 선택**(체크포인트 3): "계속(위험 감수)" → `HARNESS gate 5 --ws "WS" --accept-risk` / "중단" → 확보 필요 목록 보고 후 종료. `--yes`·`--accept-risk`면 자동 승인.
  - 그 외 사유(trace·[기입 필요]·validate) → 사유를 tp-researcher merge에 전달해 1회 재시도.
- 보고: 근거 건수 · 해결/미해결 issue · to_secure 건수 · 특허 상충 여부 · 라이선스 확인 필요 이미지 수.

### 5 DESIGN + FILL
- Agent(tp-designer). 반환에 "writer shrink 필요"가 있으면 그 반환(초과 분량·줄일 후보)을 붙여 Agent(tp-writer) `MODE=shrink` 호출 → 다시 Agent(tp-designer)(그림 data는 그대로, fillspec→fill→qa→육안 검수만; 최대 2회). 실전 기준: 실제 팀 자료는 첫 빌드가 12~14쪽이 보통이라 shrink 1회는 정상 경로다. `HARNESS gate 6 --ws "WS"` 실패 시 qa_report 사유 전달 1회 재시도.
- 보고: 쪽수 · 그림 수 · BLOCKING/WARN · 육안 검수 쪽 수 · PNG 폴더.
- 한글(COM) 주입이 불가능한 환경(맥·한글 미설치)이면: 5단계는 그림 렌더까지만 하고 `08_fill_spec.json`을 남긴 뒤 "Windows+한글 머신에서 `HARNESS fill --ws`·`qa`·6단계를 이어서"라고 안내한다. 실패가 아니다.

### 6 FINAL
- Agent(tp-finalizer). `HARNESS gate final --ws "WS"`.
- **완료 보고(고정 형식, qa_checklist D)**:
  1. 산출물 절대경로(hwp·hwpx·pdf·심사대비_패키지.md·팀_확인사항.md·qa_png)
  2. 쪽수·그림 수·표 수
  3. 모의심사 점수(항목별·합계·P/F)와 선정선 80 대비
  4. 확보 필요 목록 건수·상위 5
  5. 라이선스 확인 필요 이미지 수 → 팀_확인사항
  6. 다음 행동 3개(팀 확인사항 회신 받기 → 확보 목록 채워 `--from 4` 재실행 · 한글에서 최종 열어 날인·파일명 규칙 적용 · 5분 발표영상 대본 연습)

## 실패·재개
- 단계 실패 시 `HARNESS status --ws "WS"`를 보여주고 `--resume`/`--from N` 안내. 산출물은 지우지 않는다.
- 에이전트가 10줄 요약 대신 장문을 반환해도 파일 존재와 게이트로 판단한다.
- 팀 답변이 추가로 들어오면(`02_team_answers.md`를 입력폴더나 WS에 넣음) `--from 4`로 재실행하면 merge가 반영한다(1·2단계 재실행은 `--from 1`).

## 하지 말 것
- 오케스트레이터가 본문·숫자·그림·표지 인적사항을 직접 쓰지 않는다. 게이트를 건너뛰지 않는다(`--accept-risk`는 사용자 승인 기록이 남는 정식 경로).
- 팀 자료에 없는 사실을 "조사해서 채우겠다"고 약속하지 않는다(팀 내부 사실은 팀만 안다 → 질문지).
- 산출물은 초안이다. "제출 가능"이라고 단정하지 않고 `팀_확인사항.md`를 반드시 안내한다.
