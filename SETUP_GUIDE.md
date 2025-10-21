# 고급 시장 분석 시스템 설치 가이드

## 주요 개선 사항

### 1. 뉴스 활용 (완전 무료)

- RSS 사용 → API 비용 $0
- Yahoo Finance, CNBC, MarketWatch, Seeking Alpha 통합
- 제한 없음, 실시간 데이터

### 2. 긍정/부정 뉴스 모두 분석

- 상승 재료뿐 아니라 하락 리스크도 파악
- 시장 영향도 평가 (High/Medium/Low)
- 방향성 분류 (Bullish/Bearish/Mixed)

### 3. 예측 피드백 시스템

- 전일 예측 vs 실제 주가 비교
- AI 기반 원인 분석 (Root Cause Analysis)
- 학습 인사이트 축적

---

## 설치 단계

### 1. 필수 라이브러리 설치

```bash
pip install google-generativeai python-dotenv notion-client feedparser yfinance
```

**라이브러리 설명**:

- `feedparser`: RSS 피드 파싱 (News API 대체)
- `yfinance`: 실제 주가 데이터 수집 (예측 검증용)
- 나머지: 기존과 동일

### 2. Notion 데이터베이스 생성

#### A. 메인 분석 데이터베이스: `시장 분석 통합`

| 속성 이름       | 타입         | 옵션                                                                                                |
| --------------- | ------------ | --------------------------------------------------------------------------------------------------- |
| `기사 제목`     | Title        | -                                                                                                   |
| `언급된 종목`   | Text         | -                                                                                                   |
| `감성분석`      | Select       | Positive, Negative, Neutral                                                                         |
| `방향성`        | Select       | Bullish, Bearish, Mixed                                                                             |
| `AI 확신 점수`  | Number       | 1-10                                                                                                |
| `시장 영향도`   | Select       | High, Medium, Low                                                                                   |
| `뉴스 카테고리` | Select       | Earnings, Product, M&A, Partnership, Regulatory, Economic, Sector Trend, Executive, Guidance, Other |
| `핵심 동인`     | Text         | 긍정 요인                                                                                           |
| `리스크 요인`   | Text         | 부정 요인                                                                                           |
| `AI 분석 요약`  | Text         | 종합 분석                                                                                           |
| `가격 촉매`     | Text         | 주가 영향 요인                                                                                      |
| `URL`           | URL          | -                                                                                                   |
| `생성일`        | Created time | -                                                                                                   |

**💡 중요: 기사 본문 저장 방법**

위 표의 속성들은 AI가 분석한 구조화된 데이터를 저장하기 위한 것입니다. 사용자가 Notion에서 `기사 제목`을 클릭했을 때 기사 본문 전체와 AI의 상세 분석을 모두 볼 수 있도록, Python 스크립트는 다음 내용을 해당 Notion 페이지의 **본문(Body)에 작성**해야 합니다:

1.  **AI 분석 요약**: `AI 분석 요약` 속성의 내용을 한 번 더 기재합니다.
2.  **상세 분석 (Detailed Analysis)**: `impact_analysis` 결과를 상세히 서술합니다.
3.  **원본 기사 내용 (Original Article)**: 수집한 기사 본문 전체를 붙여넣습니다.

이렇게 구현하면, 데이터베이스 뷰에서는 핵심 요약만 빠르게 훑어보고, 개별 페이지에 들어가면 모든 상세 정보를 확인할 수 있습니다.

#### B. 피드백 데이터베이스: `예측 검증 로그`

| 속성 이름       | 타입         | 옵션                         |
| --------------- | ------------ | ---------------------------- |
| `종목`          | Title        | -                            |
| `예측 방향`     | Select       | Bullish, Bearish, Mixed      |
| `실제 변동`     | Number       | % 단위                       |
| `정확도 점수`   | Number       | 0-100                        |
| `예측 정확`     | Checkbox     | -                            |
| `편차 심각도`   | Select       | None, Minor, Moderate, Major |
| `원인 분석`     | Text         | 예측 실패/성공 이유          |
| `시장 요인`     | Text         | 외부 변수                    |
| `학습 인사이트` | Text         | 교훈                         |
| `권장사항`      | Text         | 향후 개선 방안               |
| `검증일`        | Created time | -                            |

#### C. 주간 피드백 보고서 데이터베이스: `주간 피드백 보고서`

| 속성 이름              | 타입         | 설명                                                         |
| :--------------------- | :----------- | :----------------------------------------------------------- |
| `보고서 기간`          | Title        | 보고서가 다루는 기간 (예: "2024년 10월 3주차")               |
| `정확도`               | Text         | 전체 예측 정확도 (예: "65.0%")                               |
| `핵심 요약`            | Text         | 이번 주 학습의 가장 중요한 한 문장 요약                      |
| `실패 원인 분석`       | Text         | 실패 예측에서 발견된 공통적인 패턴 및 근본 원인              |
| `성공 비결 분석`       | Text         | 성공 예측에서 발견된 공통적인 패턴                           |
| `개선된 프롬프트 제안` | Text         | 분석 정확도를 높이기 위해 제안된 새로운 프롬프트 또는 수정안 |
| `생성일`               | Created time | 보고서 생성 날짜                                             |

### 3. .env 파일 설정

```env
# Notion 설정
NOTION_API_KEY=secret_xxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_FEEDBACK_DB_ID=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
NOTION_REPORT_DB_ID=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz

# Gemini 설정
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

```

### 4. Notion API 키 발급

1. [Notion Integrations](https://www.notion.so/my-integrations) 접속
2. "New integration" 클릭
3. 이름 입력 후 "Submit"
4. "Internal Integration Token" 복사 → `.env`의 `NOTION_API_KEY`에 붙여넣기

### 5. 데이터베이스 ID 확인

1. Notion에서 데이터베이스 페이지 열기
2. 우측 상단 "..." → "Copy link"
3. URL에서 ID 추출:
   ```
   https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
                        ↑ 이 부분이 DATABASE_ID
   ```
4. 메인 DB ID → `NOTION_DATABASE_ID`
5. 피드백 DB ID → `NOTION_FEEDBACK_DB_ID`
6. 보고서 DB ID → `NOTION_REPORT_DB_ID`

### 6. Gemini API 키 발급

1. [Google AI Studio](https://makersuite.google.com/app/apikey) 접속
2. "Get API key" 클릭
3. 키 복사 → `.env`의 `GEMINI_API_KEY`에 붙여넣기

---

## 실행 방법

### 로컬 테스트

```bash
python advanced_market_analyzer.py
```

### 예상 출력

```
======================================================================
고급 시장 분석 시스템 (긍정/부정 통합 + 예측 피드백)
======================================================================

[1단계] 전일 예측 데이터 조회...
어제 예측 데이터: 5개 종목

[2단계] 예측 정확도 검증 중...

NVDA: 예측 Bullish | 실제 +3.24%
✓ 피드백 저장: NVDA (정확도: 92%)

TSLA: 예측 Bullish | 실제 -1.87%
✓ 피드백 저장: TSLA (정확도: 45%)

[3단계] 오늘 뉴스 수집 및 분석...
✓ Yahoo Finance: 8개 수집
✓ CNBC: 8개 수집
✓ MarketWatch: 8개 수집
✓ Seeking Alpha: 8개 수집

총 32개 기사 수집 완료

[4단계] AI 종합 분석 (배치 처리)...

...

[5단계] 결과 저장...
✓ Notion 저장: AAPL - Bullish (Positive)
✓ Notion 저장: TSLA - Bearish (Negative)
✓ Notion 저장: NVDA - Bullish (Positive)

======================================================================
작업 완료!
- 수집: 32개 기사
- 분석: 32개
- 저장: 긍정 8개 | 부정 5개 | 중립 2개
- 피드백: 5개 종목 검증 완료
======================================================================
```

---

## GitHub Actions 자동화

### .github/workflows/market_analysis.yml

```yaml
name: Advanced Market Analysis

on:
  workflow_dispatch:
  schedule:
    - cron: "0 14 * * 1-5" # 월-금 오후 11시 (한국 시간)

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          pip install google-generativeai python-dotenv notion-client feedparser yfinance

      - name: Run Analysis
        env:
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
          NOTION_FEEDBACK_DB_ID: ${{ secrets.NOTION_FEEDBACK_DB_ID }}
          NOTION_REPORT_DB_ID: ${{ secrets.NOTION_REPORT_DB_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python advanced_market_analyzer.py
```

### GitHub Secrets 설정

1. GitHub 저장소 → Settings → Secrets and variables → Actions
2. "New repository secret" 클릭
3. 다음 5개 추가:
   - `NOTION_API_KEY`
   - `NOTION_DATABASE_ID`
   - `NOTION_FEEDBACK_DB_ID`
   - `NOTION_REPORT_DB_ID`
   - `GEMINI_API_KEY`

---

## 비용 분석

| 항목          | 기존              | 개선 후           | 절감      |
| ------------- | ----------------- | ----------------- | --------- |
| **뉴스 수집** | News API (제한적) | RSS 피드 (무제한) | 완전 무료 |
| **AI 분석**   | 20회/일           | 8회/일 (배치)     | 60% ↓     |
| **월간 비용** | $0 (무료 티어)    | $0 (무료 티어)    | -         |
| **제약사항**  | 24시간 뉴스만     | 제한 없음         | -         |

**결론**: 완전 무료로 더 강력한 기능 제공

---

## 주요 기능

### 1. 양방향 분석

- ✅ 상승 재료 (Bullish)
- ✅ 하락 리스크 (Bearish)
- ✅ 혼합 신호 (Mixed)

### 2. 예측 검증

- ✅ 전일 예측 자동 조회
- ✅ 실제 주가 데이터 비교
- ✅ AI 원인 분석
- ✅ 학습 인사이트 축적

### 3. 다층 필터링

```
32개 수집 → 시장영향도 필터 → 확신도 필터 → 15개 저장
```

### 4. 효율성

- 배치 처리: 4개씩 묶어 분석
- 캐싱 없음 (매일 새로운 뉴스)
- 멀티소스: 4개 RSS 통합

---

## 문제 해결

### yfinance 오류

```bash
# 최신 버전 재설치
pip install --upgrade yfinance
```

### RSS 파싱 실패

- 일부 소스 실패는 정상 (나머지 소스 계속 진행)
- 모든 소스 실패시 네트워크 확인

### Notion 저장 오류

- 데이터베이스 속성 이름 정확히 일치 확인
- Select 옵션 미리 생성 (Positive, Negative 등)

---

## 다음 단계

### 고급 기능 추가

1. **포트폴리오 추적**: 보유 종목 별도 모니터링
2. **알림 시스템**: Discord/Slack 실시간 알림
3. **시각화 대시보드**: Notion Chart로 정확도 추세
4. **백테스팅**: 과거 예측 성과 분석

### 데이터 활용

- Notion에서 "정확도 점수" 기준 정렬
- "편차 심각도" Major 케이스 집중 분석
- "학습 인사이트" 패턴 도출
