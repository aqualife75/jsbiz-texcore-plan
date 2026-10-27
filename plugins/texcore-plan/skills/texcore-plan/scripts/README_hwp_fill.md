# 한글(HWP) 주입 엔진 — `hwp_fill.py` · `prep_master.py` · `render_qa.py`

텍스코어(2026 공공기술기반 시장연계 창업탐색 지원사업, 실험실창업탐색팀) 신청서 **공식 hwp 양식**에
블록 JSON(제목·문단·불릿·표·그림·강조 박스)과 고정 표 데이터를 **한글 COM 자동화로 직접 타이핑**해 넣는다.
한글이 직접 입력하므로 줄바꿈 캐시(linesegarray)가 어긋나 글자가 겹치는 문제가 없다.

- 실행 환경: **Windows + 한글(HWP) 설치**(COM `HWPFrame.HwpObject`), Python 3.12, pywin32·lxml·pymupdf·Pillow.
  검증 머신: 한글 11.0.0.2129(한글 2020 계열), Windows 11.
- 맥·리눅스에서는 동작하지 않는다(앞 단계 산출물까지만 만들고 주입은 Windows에서).

## 1. 파일

| 파일 | 역할 |
|---|---|
| `skill/scripts/prep_master.py` | 원본 양식 hwp → 앵커 토큰을 박은 `template_master.hwpx` 1회 제작(재현 가능) |
| `skill/assets/template/template_master.hwpx` | 완성 마스터(빈 양식 6쪽, 토큰 61개) |
| `skill/assets/template/anchors.json` | 토큰 목록·위치 설명·종류(`cell`/`para`/`table_first_cell`/`trl`)·고정 표 구조·체크박스 문자열 |
| `skill/scripts/hwp_fill.py` | 주입 엔진(CLI + 라이브러리 `fill()`), 자체 완결(외부 `.claude/hwpx_com.py` 의존 없음) |
| `skill/scripts/render_qa.py` | hwpx/hwp/pdf → PDF → 쪽별 PNG + `qa_report.json/.md` |
| `tests/fill_sample.json` | 전체 블록·고정 표·TRL·체크박스·영문 섹션을 쓰는 샘플(가상 팀, 설명용 샘플) |
| `tests/fill_sample_variant.json` | 엣지 케이스(국내형=영문 삭제, 빈 특허 표+대체 문장, 행 추가, EM 행 전부 삭제, 누락 토큰 빈칸, 쪽 나눔 해제, 그림 3장+누락 그림) |
| `tests/fill_out/`, `tests/fill_out_variant/` | 결과 hwpx·hwp·pdf·`page-NN.png`·`fill_report.json`·`qa_report.*` |
| `tests/master_preview/` | 마스터 미리보기 PDF·PNG |
| `_scripts/make_fill_sample_images.py` | 샘플 그림 3장(PIL, '설명용 샘플' 표기) |
| `_scripts/run_fill_sample.py` | 샘플 회귀 테스트(fill → render_qa) |

## 2. 사용법

```bash
# (1회) 마스터 제작 — 원본 hwp는 읽기만 한다
python -X utf8 skill/scripts/prep_master.py
#   → skill/assets/template/template_master.hwpx, anchors.json, tests/master_preview/

# 채우기
python -X utf8 skill/scripts/hwp_fill.py --master skill/assets/template/template_master.hwpx \
       --spec fill_spec.json --out out/신청서.hwpx --hwp out/신청서.hwp --pdf out/신청서.pdf [--report out/fill_report.json]

# 검수(PDF가 이미 있으면 --pdf 로 COM 렌더 생략)
python -X utf8 skill/scripts/render_qa.py --src out/신청서.hwpx --out out/qa --pdf out/신청서.pdf [--dpi 110]

# 샘플 회귀
python -X utf8 _scripts/make_fill_sample_images.py
python -X utf8 _scripts/run_fill_sample.py
python -X utf8 _scripts/run_fill_sample.py --spec tests/fill_sample_variant.json --out tests/fill_out_variant --name variant_filled

# 멈췄을 때: 창 없는(자동화가 남긴) Hwp 프로세스만 정리(사용자가 띄운 한글 창은 보존)
python -X utf8 skill/scripts/hwp_fill.py --kill
```

라이브러리: `from hwp_fill import fill; rep = fill(master, spec_or_path, out, hwp=None, pdf=None)`
→ `{out, hwp, pdf, pages, leftover_tokens, warnings, sections_filled, tables, images, seconds}`.
`from render_qa import render; qa = render(src, out_dir, dpi=110, pdf=None)` → `{pages, over_limit, leftover_tokens, blocking, warnings, info, sections, page_detail, png, pass}`.
CLI 종료코드: `hwp_fill` 남은 토큰 있으면 1, `render_qa` BLOCKING 있으면 2.

## 3. 마스터의 앵커 토큰(요약 — 전체는 `anchors.json`)

| 종류 | 토큰 | 채우는 방법 |
|---|---|---|
| 표지 값 칸 | `CV_ORG` `CV_UNIV` `CV_GRI` `CV_ADDR` `CV_TEAM_KO` `CV_TEAM_EN` `CV_ITEM_KO` `CV_ITEM_EN` `CV_FIELD` `CV_MFG` `CV_NONMFG` `CV_DATE`, `EL_/PM_/PI_` × `NAME BIRTH ORG MAJOR DEGREE TEL PHONE EMAIL` | `replacements`(AllReplace) |
| 체크박스 | 토큰 없음 — `□수도권` `□충청권` `□대경권` `□호남권` `□동남권` `□여성특화형` `□출연(연)특화형` `□ 해외교육형` `□ 국내교육형` `□ 여성특화형` `□ 출연(연)특화형` | `replacements`에 `"□충청권": "■충청권"` (띄어쓰기 차이 주의: 신청혁신단 칸은 붙여 쓰고, 교육유형 칸은 한 칸 띔) |
| 본문 앵커 | `S_I1` `S_I2` `S_II1` `S_II2_PLAN` `S_II2_UPGRADE` `S_III1` `S_III2` `S_III3` `S_EN1` `S_EN2` `S_EN3` | `sections`(블록 타이핑) |
| 고정 표 | `T_PATENTS`(9열) `T_OTHERIP`(5열) `T_IPREL`(6열) `T_TEAM`(9열, 라벨 열 유지) `T_CAREER`(6열, 라벨 열 유지) | `tables` |
| TRL | `TRL_1`…`TRL_9` | `trl.level` |

마스터에서 바뀐 점: 작성요령 박스 11개·표지 `<작성 시 주의 사항>` 박스·`※ 탐색팀의 국문명은…(제출 시 삭제)` 삭제 /
Ⅰ-2의 □ 소제목 4개 제거(heading 블록으로 다시 씀) / 표 안 예시(`<예> …`, `-`) 삭제 /
`□ 핵심기술의 권리인 및 발명자와의 관계` 앞 강제 쪽 나눔 해제 / 양식 제목 24개에 '다음 문단과 함께'.
**남긴 양식 주석**: Ⅱ-2-1 표 아래 `※` 3줄, TRL `※ TRL 9단계…`, Ⅳ `※ EL 또는 EM이 졸업생일 경우…` 박스와 주석 2줄.
기술분야 칸은 파란 안내문을 남기고 그 아래 줄에 `{{CV_FIELD}}`.

## 4. `fill_spec.json` 계약

```json
{
 "replacements": {"{{CV_ORG}}": "충북대학교", "□충청권": "■충청권", "{{CV_DATE}}": "2026년 1월 15일"},
 "sections": {"S_I1": [블록...], "...": []},
 "tables": {
   "T_PATENTS": {"rows": [["특허명","출원년도","출원국","출원번호","출원인","등록년도","등록국","등록번호","등록인"]],
                 "delete_if_empty": true, "empty_text": "(선택) 표 대신 넣을 문장"},
   "T_TEAM": {"rows": [["EL","성명","생년월일","소속/학과","최종학위/현재학적","핸드폰","이메일","EL과의 관계","성별"]],
              "keep_first_col": true, "font_pt": 9}
 },
 "trl": {"level": 4},
 "delete_english_section": false,
 "font": {"body_pt": 10, "table_pt": 9, "caption_pt": 8.5},
 "remove_page_breaks": false,
 "clear_unfilled": false
}
```

- `replacements`: 모두 AllReplace(문서 전체). 값 `""`도 가능.
- `tables`:
  - 앵커 셀부터 오른쪽으로 채우고 다음 행으로. 표 행이 모자라면 `TableAppendRow`.
  - `keep_first_col`(T_TEAM·T_CAREER 기본 true): 각 행 첫 값은 **라벨**(EL/PM/PI/EM) — 같은 라벨의 표 행에 배정, 남는 데이터는 행을 추가하고 라벨도 입력.
    데이터 없는 **EM 행은 삭제**, 데이터 없는 EL/PM/PI 행은 비워 두고 경고.
  - 일반 표는 남는 빈 행을 지운다(`trim_empty_rows`, 기본 true).
  - `delete_if_empty` + 빈 `rows` → 표와 표 바로 위 `□` 제목 문단까지 삭제(표 아래 `※` 주석은 남음). `empty_text`가 있으면 제목은 두고 표 자리에 그 문장.
  - 값 안 `\n`은 칸 안 줄바꿈. 칸 폭보다 길 것 같은 값은 자동으로 장평 88%·자간 -6%.
  - `font_pt`로 표별 글자 크기(기본 `font.table_pt`).
- `trl.level`: 해당 칸 `( √ )`, 나머지 `(    )`.
- `delete_english_section: true`: `Summary of Business Start-up Item` 상자부터 문서 끝까지 삭제(이때 `S_EN*` 섹션은 무시).
- `remove_page_breaks`(선택): Ⅲ·Ⅳ 장 시작의 강제 쪽 나눔 해제 — 10쪽 초과 시 1차 압축 수단.
- `clear_unfilled`(선택): 채우지 않은 `{{토큰}}`을 빈칸 처리하고 경고로 남김(기본은 남은 토큰 = BLOCKING).
- `sections`에 없는 섹션 앵커는 비우고 경고(QA가 빈 섹션으로 잡음).
- `font` 추가 키(선택): `heading_pt`(12) `subheading_pt`(10.5) `face`("맑은 고딕") `heading_face`("휴먼명조", 양식 □ 제목과 같은 글꼴) `line_pct`(160) `table_line_pct`(130).

### 블록 타입

| type | 필드 | 결과 |
|---|---|---|
| `heading` | `text` | 휴먼명조 굵게 12pt(양식 □ 제목과 같은 계열), 다음 문단과 함께 |
| `subheading` | `text` | 맑은 고딕 굵게 10.5pt, 다음 문단과 함께 |
| `para` | `text`, `align`(선택), `bold`(선택) | 본문 10pt·160%. `\n`은 문단 나눔, `**굵게**` 지원. 영문 비율 85%↑이면 자동 왼쪽 정렬 |
| `bullets` | `items`: 문자열 또는 `{"text","level":2}` | `- `(2단계 `· `) + 내어쓰기. 이미 `-·•※→①□` 등으로 시작하면 표식 생략 |
| `table` | `caption` `columns` `rows` `col_widths_mm`(선택, 비율로 170mm에 맞춤) `source` `font_pt` | 캡션(가운데·굵게·작게, 다음 문단과 함께) + 단 폭 표(머리행 굵게·회색 채움·가운데) + 출처(작게·회색). 열 폭 미지정 시 글자 길이로 자동 배분(최소 12mm), 짧은 값 열은 가운데 정렬 |
| `figure` | `caption` `images`:[{`path`,`width_mm`,`max_height_mm`,`label`}] `proves` `source` | 표 프레임 방식: 그림 수만큼 열인 1행 표(테두리 없음)에 그림(글자처럼 취급, mm 지정, 비율 유지, 칸 폭 안) + 아래 병합 행에 캡션·`→ 증명`(남색 굵게)·출처(회색). 경로는 spec 파일 폴더 기준 상대경로 가능, 없는 그림은 경고+자리 문구 |
| `callout` | `text`, `font_pt` | 1×1 표, `#F1F5F9` 채움, 회색 테두리, 굵게 |
| `spacer` | `pt`(선택, 기본 6) | 빈 문단 |

## 5. 기술 확인 결과(실험으로 검증, 2026-10-27)

| # | 질문 | 결과 |
|---|---|---|
| ① | 선택 상태에서 InsertText가 선택을 대체하나 | **대체한다**(찾기로 선택한 `□ … 컨셉`이 입력 문자열로 바뀜, XML 확인). 엔진은 명확성을 위해 찾기 → `Delete` → 입력 |
| ② | 선택 없이 CharShape → 이후 타이핑에 적용되나 | **적용된다**(굵게16pt빨강 → 새 charPr 생성 확인). 단 **표 셀은 표 만들기 전 글자 모양을 물려받지 않는다**(셀은 바탕글 기본 글꼴) → 셀마다 글자·문단 모양을 다시 지정 |
| ③ | TableCreate 파라미터 | `Rows` `Cols` `WidthType=2`(임의) `HeightType=0`(자동) `WidthValue` `CreateItemArray("ColWidth", n)`; **ColWidth는 셀 안쪽 여백(510×2=1020 HWPUNIT≈3.6mm)을 뺀 폭**(30mm 지정 → 실제 셀 9523=33.6mm). `TableProperties.TreatAsChar=1`, `OutsideMarginLeft/Right/Top/Bottom=0`(기본 1mm 바깥 여백 때문에 단 폭 표가 2mm 넘침). 생성 직후 커서는 A1 |
| ④ | 셀 이동·표 밖으로 | `TableRightCell`은 행 끝에서 다음 행 첫 칸으로 넘어가고, **마지막 칸에서는 행을 추가하지 않고 제자리**(→ `TableAppendRow`: 현재 행 아래 추가·커서 이동, `TableDeleteRow`: 현재 행 삭제). `TableColBegin`+`TableColPageUp`=A1, `TableLowerCell`/`TableRightCell`로 이동. **`CloseEx`는 표가 든 문단의 맨 앞(표 앞, pos 0)으로 나간다** → `MoveParaEnd` 후 `BreakPara`로 이어 쓰기. 표 전체 삭제는 셀 안에서 `ParentCtrl` 확보 → `CloseEx` → `DeleteCtrl(ctrl)` |
| ⑤ | InsertPicture 크기 단위·글자처럼 취급 | `InsertPicture(path, True, 1, False, False, 0, W, H)`: sizeoption=1이면 **W·H 단위 mm**(50 → 14173 HWPUNIT). 반환 ctrl의 `Properties.Item("TreatAsChar")` 기본 1(본문·셀 모두), 엔진이 한 번 더 보장 |
| ⑥ | 셀 배경·글자 크기 | `CellBorderFill`은 **블록 없이 실행하면 현재 셀**에 적용. 채움: `FillAttr.type=BrushType("NullBrush|WinBrush")`, `WinBrushFaceColor=RGBColor(..)`. 테두리: `HSet.SetItem("BorderType/BorderWidth/BorderColor"+Left/Right/Top/Bottom)`(속성 대입 `BorderCorlorRight`는 실패, `BorderColor*`를 SetItem). **셀 블록의 안쪽 선은 `TypeHorz/TypeVert/WidthHorz/WidthVert/ColorHorz/ColorVert`를 같이 줘야 바뀐다**(없으면 바깥선만). 셀 블록: `TableCellBlock`→`TableCellBlockExtend`→`TableColPageDown`/`TableColEnd`, 병합 `TableMergeCell`. 글자 크기 `CharShape.Height = pt×100`, 장평 `Ratio*`, 자간 `Spacing*` |
| ⑦ | 한글·공백 경로 | 임시 폴더 안에서는 한글·공백·`00. A_B_정석Biz` 같은 경로도 Open·SaveAs·InsertPicture 모두 정상. **그러나 Dropbox 폴더에 있는 그림을 InsertPicture 하거나, 그림이 든 문서를 Dropbox 폴더로 SaveAs 하면 한글이 숨은 대화상자에서 무한 대기**(같은 경로 구조를 임시 폴더에 만들면 정상 → 위치 문제, 보안 확인 모듈 `FilePathCheckDLL` 미등록 탓으로 추정 — `RegisterModule`이 False). → 엔진은 **모든 COM 입출력을 세션 임시 폴더로** 하고(마스터·그림 사본, 결과 저장) 파이썬이 최종 위치로 복사 |

추가로 실측한 함정과 대응:
- **자동 서식**: InsertText로 친 메일·URL은 파란 밑줄 하이퍼링크가 되고, 표 칸의 `1998.03.02` 같은 날짜는 끝에 `.`이 붙는다 → 그런 조각은 `{{_L001}}` 자리표시를 입력하고 마지막에 AllReplace로 바꾼다(AllReplace는 자동 서식이 안 걸림).
- **세션 연속 실행 경합**: 직전 세션이 Quit 중인 프로세스에 새 Dispatch가 붙으면 멈춘 사례가 있어, 세션 시작·종료 때 창 없는 Hwp가 사라질 때까지 기다리고(남으면 강제 종료) 시작한다.
- **워치독**: 숨은 대화상자로 COM 호출이 멈추면 600초(환경변수 `TP_HWP_TIMEOUT`) 뒤 창 없는 Hwp를 종료해 예외로 풀고 문서·프로세스를 정리한다.
- `SetMessageBoxMode(0x22011)`: 확인→OK, 예/아니오(/취소)→아니오로 자동 응답.
- `RepeatFind`는 표 셀 안 글도 찾고 커서가 그 셀로 들어간다. `GetTextFile("TEXT")`는 표 셀 글까지 포함 → 남은 토큰 검사에 사용.
- COM 문단 번호(`GetPos()[1]`)는 hwpx `section0.xml`의 최상위 `<hp:p>` 순서와 같다.
- 한글이 저장한 hwpx도 편집된 문단에는 linesegarray를 쓰지 않으며, linesegarray 없는 문단은 한글이 열 때 다시 계산한다(마스터 제작에 활용).
- pymupdf 기본 텍스트 순서는 표 안 글(콜아웃 등)을 쪽 끝으로 미룬다 → `render_qa`는 `get_text(sort=True)`.

## 6. 검증 결과(샘플)

| 테스트 | 결과 |
|---|---|
| `prep_master.py` | 원본 7쪽 → 마스터 6쪽, 토큰 61개, 작성요령·주의사항 박스 12개 삭제, 정규화 후 토큰 쪼개짐 0 |
| `fill_sample.json` | **7쪽**, 그림 3개, 남은 토큰 0, 경고 0, QA BLOCKING 0, 약 26초. `.hwp`도 7쪽으로 렌더 확인 |
| `fill_sample_variant.json` | 5쪽, 영문 섹션 삭제·빈 특허 표 대체 문장·기타 IP 행 추가(5행)·EM 4명(행 추가+라벨)·경력 표 EM 3행 삭제·누락 그림 경고·누락 토큰 10개 빈칸 처리 확인 |
| PNG 육안 검수(3회 반복) | 1회차 지적 → 수정: 그림 프레임 안쪽 선, 표 캡션이 쪽 끝에 홀로 남음, 메일 하이퍼링크, 날짜 끝 `.`, 좁은 칸 3~4줄 줄바꿈, 영문 문단 단어 간격. 2회차 지적 → 수정: 양식 `□` 제목이 쪽 끝에 홀로 남음(마스터 제목 24개 다음 문단과 함께), QA 텍스트 순서. 3회차: 표지 ■ 전환, 작성요령 삭제, 표·그림 크기·캡션, 겹침·잘림 없음 확인 |

## 7. 알려진 제한

- Windows + 한글 설치 머신 전용. `kill_orphans`는 **창 없는 Hwp 프로세스를 모두** 종료하므로 다른 한글 자동화와 동시에 돌리지 말 것(사용자가 띄운 한글 창은 보존).
- 엔진이 만드는 표·그림 프레임은 '글자처럼 취급'이라 **쪽 경계에서 나뉘지 않는다** — 반 쪽을 넘는 긴 표는 블록을 둘로 나눠 쓸 것(안 그러면 통째로 다음 쪽으로 넘어가 빈 공간이 생김).
- 고정 표 이동은 데이터 영역에 병합 셀이 없는 격자를 전제(이 양식은 해당). 양식 고정 칸이 좁아(핸드폰·이메일·출원인) 자동 축소 후에도 2~3줄로 줄바꿈될 수 있다 — 짧게 쓰거나 `\n`으로 끊을 것.
- 인라인 서식은 `**굵게**`만 지원(기울임·밑줄·색 없음). 그림은 한 행에 나란히(3장 이상이면 작아짐).
- Ⅲ·Ⅳ 장 시작 강제 쪽 나눔은 양식대로 유지 — 10쪽 초과 시 `remove_page_breaks: true` 또는 본문 압축.
- 쪽수는 한글 `PageCount`·PDF 기준. 블록 순서·분량 조절(10쪽 예산)은 앞 단계(writer/designer)의 몫이다.
