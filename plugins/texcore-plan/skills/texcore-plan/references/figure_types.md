# 생성 도식 11종 — `figures[].type`과 `data` 스키마 (tp-writer 계획 · tp-designer 데이터 작성 · make_figures.py 렌더)

공통: `{"id":"fig_xxx","type":"<type>","section_id":"S_I2","width_px":1600,"font_scale":1.3,"width_mm":150,"caption":"[그림 n] …","source":"출처 …","proves":"→ 증명: …","data":{…}}`
- `font_scale` 기본 1.3(생략 시 harness가 1.3 적용): 1600px 폭을 150mm로 넣을 때 본문 글자가 약 9pt가 되는 하한. 나란히 74mm로 넣는 그림은 `width_px` 800·`font_scale` 1.3, 또는 1600·1.6으로 글자를 키운다.
- 생성 PNG의 DPI 메타데이터는 1600px=150mm 기준이라 한글에 '원래 크기'로 넣으면 그림마다 글자 크기가 같다.
라벨 20자 이내, 한 칸 한 사실, 숫자는 사실 팩·증거에 있는 값만(trace 검사). 가상 값이면 라벨에 "(설명용 예시)".

| type | data | 쓰는 곳 |
|---|---|---|
| `competitor_matrix` | `{"criteria":[{"name":"…","why":"비교 이유 한 줄"}], "competitors":[{"name":"…","is_us":true|false,"cells":["O"|"△"|"X"|"텍스트"]}], "note":"비교 기준·측정 조건·출처"}` — 행=기준, 열=경쟁사, 우리 열 강조, 우리 열에 X 1개 이상 | Ⅰ-2c |
| `tam_sam_som` | `{"tam":{"label","value","calc","source"},"sam":{…},"som":{…},"note":"…"}` | Ⅰ-2d |
| `tech_concept` | `{"problem":"고객이 못 하는 일","components":[{"name":"덩어리","desc":"쉬운 말 한 줄","evidence":"특허 10-…/논문/시험값"}],"outcome":"고객의 변화","image":"선택: 팀 이미지 경로"}` (덩어리 3~4) | Ⅱ-1, Ⅰ-2a(제품 이미지 없을 때) |
| `trl_ladder` | `{"current":4,"target":6,"evidence_current":"…","evidence_target":"…(기간)","track":"공통"}` | Ⅱ-2-2 |
| `gantt_milestones` | `{"start":"2026-04","months":12,"rows":[{"name":"제품","bars":[{"from":1,"to":3,"label":"…"}],"milestones":[{"month":3,"label":"인터뷰 20건"}]}],"hidden_schedule":[{"month":9,"label":"인증 컨설팅 착수"}],"roadmap":[{"period":"2027","text":"…"}]}` — 행 4줄(제품·고객·인증·자금), ◆ 6개, 숨은 일정 | Ⅲ-2 |
| `cost_table` | `{"items":[{"name","qty","unit_price","amount","basis"}],"total":"…","funding_split":[{"label":"지원 예산","amount"},{"label":"자부담","amount"}]}` | Ⅲ-1 |
| `team_org` | `{"members":[{"role":"EL","name","affil","expertise","duty":"역할 한 줄"}],"partners":[{"name","role"}]}` | Ⅳ |
| `evidence_card` | `{"image":"경로","label":"증거 1","caption":"무엇이 보이는가","proves":"→ 증명: …","source":"출처"}` | 모든 섹션(팀 사진·시험 결과·캡처) |
| `evidence_board` | `{"items":[evidence_card data × 2~3]}` | Ⅱ-1 제3자 검증, Ⅳ 실적 |
| `kpi_strip` | `{"items":[{"value":"8,000","unit":"만 명","label":"…","source":"…","highlight":true}]}` (3~4개) | Ⅰ-2a 고통의 크기, Ⅲ-2 고객의 계산 |
| `prototype_stages` | `{"stages":[{"name":"목업","what":"…","verifies":"…","success":"숫자 기준","trl":"3","current":true}]}` (3~4단계) | Ⅲ-1 |
| `customer_profile` | `{"primary":{"who","situation","pain","current_alt","wtp"},"secondary":{…}}` | Ⅰ-2b |

렌더: `harness figures --ws WS` → `08_figures/{id}.png` + `figures_report.json`. 실패한 그림은 `[그림 렌더 실패]` 문단으로 대체되므로 반드시 report를 확인하고 data를 고쳐 재실행한다.
