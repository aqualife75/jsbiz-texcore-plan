# 근거·이미지 수집 정책 (tp-researcher)

## 등급
| Tier | 무엇 | 사용 | image_ledger.license |
|---|---|---|---|
| A | 팀 제출 자료의 숫자·이미지·인터뷰 기록 | 그대로(가공 금지) | `team` |
| B | 인용한 기사·논문·통계·특허 페이지의 해당 문단/figure **캡처**(`scripts/capture_evidence.py`) + 숫자는 도식으로 재작성 | 출처줄 필수 | `quote` |
| C | 웹 이미지(제품·현장·경쟁사 화면) | 수집·배치 허용(사용자 결정 2026-09-11), 확인되면 `cc/public/official`, 아니면 `unknown`+`needs_human_review` → `팀_확인사항.md` 표 | `cc`·`public`·`official`·`unknown` |
| G | 생성 도식(make_figures) | 입력 숫자의 출처를 캡션에 | `generated` |

## 조사 채널
- 시장·통계: 통계청 KOSIS·e-나라지표·부처 보도자료·백서, 협회 통계, 시장조사 리포트 요약 페이지(Grand View·MarketsandMarkets·Statista 등은 요약 수치만, 원출처 표기).
- 정책: K-Startup 공고문, 과기정통부·산업부·복지부 보도자료(실제 문서·쪽수).
- 논문: Semantic Scholar API(`https://api.semanticscholar.org/graph/v1/paper/search?query=...&fields=title,year,venue,abstract,url,openAccessPdf`), Google Scholar, KCI, PubMed. 오픈액세스 figure 우선.
- **특허: KIPRIS(`http://www.kipris.or.kr`) — 출원번호·출원인·발명자·법적 상태를 반드시 확인해 Ⅱ-2-1 표와 대조**. 팀이 적은 번호와 다르면 issue로.
- 경쟁사·대체재: 공식 사이트·앱스토어·가격 페이지 캡처.
- 규제·인증: 식약처(의료기기 등급·GMP), KC(국가기술표준원), FDA(510(k)/De Novo/PMA) 공식 안내 — 숨은 일정의 근거.
- 벤치마크: 유사 실험실 창업 사례(상장 IR·공시) — Ⅲ-2 로드맵의 현실성 근거.

## 슬롯별 최소 근거
| 슬롯 | 최소 | 외부 조사 |
|---|---|---|
| I-2a 컨셉 | 제품/개념 이미지 1(팀) | ✕ |
| I-2b 고객 | 인터뷰·현장 증거(팀) — **외부 대체 금지** | ✕ (고객 수 통계만 ●) |
| I-2c 차별성 | 경쟁사 2~3 공식 페이지·가격 캡처 | ● |
| I-2d 시장 | 공식 통계 2 + 산식 + (해외형) 미국 시장 1 + 규제 1 | ● |
| II-1 기술 | 논문·특허·시험 결과(팀 우선), 제3자 검증 1 | ● 기술 근거·제3자만 |
| II-2a IP | KIPRIS 조회 결과(출원번호·권리인) | ● 필수 |
| II-2b TRL | 팀 증거 | ✕ |
| III-1 시제품 | 비용 단가 근거(견적·시장가) | △ |
| III-2 일정 | 인증·허가 요건·소요 기간 1 + 유사 사례 일정 1 | ● |
| IV 팀 | 팀 자료. 공식 프로필·논문 확인만 | △ |
| EN | — | ✕ |

## 원장 필드
- `evidence.json.records[]`: id(E01…), slot_id, section_id, claim, value, unit, asof, source_title, publisher, url, retrieved, tier, capture_file, quote(원문 1~2문장), confidence
- `image_ledger.json.images[]`: file, url, page_url, title, author, license, license_note, retrieved, used_in_sections[], needs_human_review
- `search_log[]`: slot_id, query, channel, result(찾음/못 찾음/상충)

## 인용 형식(본문·캡션 출처줄)
`출처: 발행처 「제목」 (기준 YYYY.MM)` — 여러 개는 ` · `로. URL은 원장에만. 수집일은 원장에.

## 금지
- 팀 내부 사실(인터뷰·시제품·팀·가격 결정·첫 고객)을 외부 자료로 대체.
- 출처를 특정할 수 없는 숫자(블로그 재인용)는 confidence low → 원출처를 찾고, 못 찾으면 `[확보 필요]`.
- 가짜 로고·가짜 리뷰·가짜 수치·가짜 특허번호 생성. "인터넷 전체를 조사했다"는 주장(검색 범위와 한계를 search_log에).
