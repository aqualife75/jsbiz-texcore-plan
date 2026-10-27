# 고급 안내 — 강사·기존 사용자용 (v{VERSION})

교육생은 [사용설명서](../사용설명서.html)의 세 단계로 충분합니다. 이 문서는 폴더 구조, 수동 실행, Windows 한글 주입, 문제 해결을 다룹니다.

## 폴더 구조

```
정석biz-텍스코어-프로젝트/
├─ AGENTS.md                      Codex 루트 지침(총괄 역할)
├─ .agents/skills/texcore-plan/   스킬: SKILL.md(6단계 오케스트레이션) · references/ · assets/(양식 템플릿·스키마) · scripts/(하네스)
├─ .codex/agents/tp_*.toml        역할 6개: intake · writer · panel · researcher · designer · finalizer
├─ 자료넣는곳/                     한 팀의 자료(입력)
├─ work/                          워크스페이스 YYYY.MM.DD_팀_TexcorePlan(단계별 산출물) · setup/runtime.json(환경)
├─ 결과물/                         게시된 결과(날짜별) · 결과보기.html
├─ examples/                      교육용 가상 팀 '진동지기' 자료와 미리보기
└─ project.json · requirements.txt · 사용설명서.html · docs/
```

워크스페이스 안: `01_extract/`(추출 텍스트·이미지) → `02_fact_pack.json`·`02_team_questions.md` → `03_outline.json` → `04_draft_v1.json` → `05_review/summary.json` → `06_evidence/` → `07_draft_v2.json` → `08_figures/`·`08_fill_spec.json` → `09_build/`(hwpx·pdf·qa) → `10_final/`.

## 수동 실행(Codex 없이 하네스만)

`work/setup/runtime.json`의 `python`으로:

```
python .agents/skills/texcore-plan/scripts/prepare_project.py --project . --install-missing
python .agents/skills/texcore-plan/scripts/harness.py init 자료넣는곳 --out work --team 팀명 --type 해외
python .agents/skills/texcore-plan/scripts/harness.py extract --ws work/<WS>
# (에이전트 단계) validate · trace · gate 2~5
python .agents/skills/texcore-plan/scripts/harness.py figures --ws work/<WS>
python .agents/skills/texcore-plan/scripts/harness.py fillspec --ws work/<WS>
python .agents/skills/texcore-plan/scripts/harness.py fill --ws work/<WS>      # Windows + 한글
python .agents/skills/texcore-plan/scripts/harness.py qa --ws work/<WS>
python .agents/skills/texcore-plan/scripts/harness.py final --ws work/<WS>
python .agents/skills/texcore-plan/scripts/publish_results.py --project . --ws work/<WS>
```

`harness.py status --ws <WS>`로 단계·게이트 상태를 봅니다. 에이전트 단계(사실 팩·목차·본문·모의심사·조사)는 Codex가 `.codex/agents/*.toml`의 역할로 수행합니다.

## Windows + 한글에서 마무리

한글이 없는 환경에서 5단계까지 끝난 프로젝트 폴더를 Windows로 옮긴 뒤(폴더 전체), 한글을 설치한 상태에서 PowerShell로:

```
python .agents\skills\texcore-plan\scripts\finish_in_hwp.py --project .
```

주입 → 쪽 검수 → 최종 복사 → 게시를 한 번에 합니다. Codex 안에서 실행할 때 COM 호출이 샌드박스에 막히면 Codex가 승인을 요청하거나 이 명령을 안내합니다. 한글이 멈추면 `python .agents\skills\texcore-plan\scripts\hwp_fill.py --kill`로 창 없는 한글 프로세스를 정리합니다.

## 쪽수 조정 경로

실제 팀 자료는 첫 빌드가 12~14쪽이 보통입니다. 순서: 그림 폭 축소 → `harness.py fillspec --remove-page-breaks`(Ⅲ·Ⅳ 장 강제 쪽 나눔 해제) → `08_fill_options.json`에 `{"font": {"line_pct": 150, "table_line_pct": 125}}` → tp_writer `MODE=shrink`(그림과 중복되는 불릿 제거). 쪽 아래가 비는 원인은 대개 '글자처럼 취급' 표가 통째로 다음 쪽으로 넘어간 것이며, 그 표의 행·셀 글자를 줄이면 한 쪽이 돌아옵니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| 준비 단계에서 패키지 설치 실패 | 인터넷 연결·프록시 확인 후 "환경 준비를 다시 확인해줘". `work/setup/setup-*.log`에 원인 기록 |
| hwp 파일 추출 0자 | 한글에서 PDF 또는 hwpx로 저장해 자료넣는곳에 추가 후 "이어서 해줘" |
| 도식 렌더 실패 | Chrome/Edge 설치 확인. `08_figures/figures_report.json`의 error 확인 |
| 한글 주입 중 멈춤 | Dropbox·OneDrive 동기화 폴더에서 실행하면 숨은 대화상자로 멈출 수 있음 → 로컬 폴더로 옮겨 실행. `hwp_fill.py --kill` |
| 10쪽 초과 | 위 '쪽수 조정 경로' |
| 모의심사 점수가 낮음 | `05_review/summary.json`의 to_reach_85 처방 → 팀 답변·자료 보강 후 "4단계부터 다시" |

## 연도 갱신

공고가 바뀌면 `.agents/skills/texcore-plan/assets/template/`의 원본 양식과 `references/evaluation_guide.md`·`form_map.md`를 새 공고로 갱신하고 `scripts/prep_master.py`로 템플릿 마스터를 다시 만듭니다. 최신 패키지는 https://github.com/aqualife75/jsbiz-texcore-plan 의 Releases에서 받습니다.
