# AI 기반 시장 주도주 발굴 및 피드백 시스템 구축 가이드

## 1. 개요

이 가이드는 시장의 뉴스 흐름 속에서 AI를 활용해 '상승 또는 하락 잠재력이 큰 주식'의 단서를 능동적으로 발굴하고, 그 결과를 스스로 피드백하여 분석 정확도를 높여가는 자동화 시스템 구축을 목표로 합니다.

이 시스템은 단순히 주가 변동을 '예측'하는 것을 넘어, 다음과 같은 역할을 수행하는 **'지능형 금융 리서치 어시스턴트'**를 지향합니다.

-   **양방향 기회 포착**: 긍정적 뉴스(상승 동력)와 부정적 뉴스(하락 동력)를 모두 분석하여 시장의 전체적인 흐름을 조망합니다.
-   **비용 효율성**: Google AI Studio의 무료 사용량(분당 2회, 하루 50회)에 맞춰 **RSS, Yahoo Finance** 등 비용 효율적인 API를 우선적으로 사용합니다.
-   **자동 피드백 루프**: 전날의 분석과 실제 시장 결과를 비교하여, 예측이 빗나갔을 경우 그 원인을 스스로 분석하고 학습합니다.

## 2. 시스템 아키텍처

**무료 정보 소스 (RSS, Yahoo Finance)** → **GitHub Actions** (스케줄러) → **Python Script** (Gemini 종합 분석 및 피드백) → **Notion** (결과 저장 및 대시보드)

## 3. 사전 준비

### A. Notion 데이터베이스 설계

분석 및 피드백 결과를 저장할 Notion 데이터베이스를 아래와 같이 구성합니다.

**데이터베이스 이름**: `AI 시장 분석 및 피드백 (AI Market Analysis & Feedback)`

| 속성 이름 | 타입 | 설명 |
| :--- | :--- | :--- |
| `기사 제목` | `Title` | 수집된 기사 또는 분석 주제 |
| `언급된 종목` | `Text` | Gemini가 찾아낸 주식 티커 (예: NVDA, TSLA) |
| `AI 분석 요약` | `Text` | Gemini의 종합 분석 내용 |
| `감성분석` | `Select` | `Positive` (호재), `Negative` (악재) |
| `AI 확신 점수` | `Number` | 이 뉴스가 주가에 영향을 미칠 확률 (1~10점) |
| `뉴스 카테고리` | `Select` | 뉴스 유형 (예: 실적, 신제품, M&A, 거시경제) |
| `피드백 분석` | `Text` | (익일 실행) 전날 분석과 실제 결과의 차이점에 대한 AI의 원인 분석 |
| `URL` | `URL` | 기사 원문 링크 |
| `분석일` | `Created time`| 정보가 기록된 날짜 |

### B. API 키 발급 및 라이브러리 설치

#### **1. 라이브러리 설치**
```bash
pip install google-generativeai python-dotenv notion-client feedparser yfinance
```
*   `feedparser`: RSS 피드를 쉽게 파싱하기 위한 라이브러리
*   `yfinance`: Yahoo Finance에서 주가 데이터를 가져오기 위한 라이브러리

#### **2. .env 파일 생성**
프로젝트 폴더에 `.env` 파일을 만들고 아래 내용을 준비합니다. NewsAPI는 이제 선택 사항입니다.
```
# .env
NOTION_API_KEY=""
NOTION_DATABASE_ID=""
GEMINI_API_KEY=""
# NEWS_API_KEY="" (선택 사항)
```

## 4. 핵심 Gemini 프롬프트 설계 (자기 개선형 시장 분석가)

이 프롬프트는 단순 분석을 넘어, 과거의 분석을 참고하여 스스로의 판단을 개선하는 '피드백' 기능을 포함합니다.

#### 배치 처리를 통한 API 호출 최적화

API 호출을 최소화하고 효율을 극대화하기 위해, 여러 기사(예: 4-8개)를 하나의 프롬프트에 담아 한 번에 분석을 요청합니다. AI는 각 기사에 대한 분석 결과를 JSON 객체 배열로 반환해야 합니다.

```python
def get_batch_analysis_prompt(articles):
    # articles는 [{'title': '...', 'content': '...'}, ...] 형태의 딕셔너리 리스트입니다.

    article_inputs = []
    for i, article in enumerate(articles):
        article_inputs.append(f"""
        <article index="{i}">
        <title>{article['title']}</title>
        <content>{article['content'][:3500]}</content>
        </article>
        """)

    return f'''
    You are a top-tier analyst at Goldman Sachs. Your task is to analyze a batch of news articles and return a JSON array where each object represents the analysis for one article.

    ### Articles to Analyze:
    {''.join(article_inputs)}

    ### Analysis Instructions:

    Analyze each article provided above and provide your findings as an array of JSON objects. The length of the array MUST match the number of articles provided.
    The JSON object for each article should follow this exact format:

    {{
      "article_index": <int>, // The index of the article from the input
      "mentioned_tickers": ["Identify all publicly traded stock tickers (e.g., 'AAPL', 'MSFT'). If none, return an empty array []."],
      "summary": "Summarize the key points of the article in 3-4 sentences in KOREAN, focusing on market impact.",
      "sentiment": "Analyze the overall tone. Respond with only one: 'Positive', 'Negative', or 'Neutral'.",
      "news_category": "Categorize the news. Choose one from: 'Earnings', 'Product Launch', 'M&A', 'Partnership', 'Regulatory', 'Macroeconomic', 'Executive Change', 'Other'.",
      "impact_analysis": "Analyze in KOREAN the potential short-term impact of this news on the stock price. Explain the key drivers for both upside and downside.",
      "conviction_score": "On a scale of 1 to 10, how confident are you that this news is a significant catalyst? Provide only an integer."
    }}

    Return ONLY the JSON array. Do not include any other text or markdown formatting.
    '''
```

## 5. 주간 피드백 보고서 및 프롬프트 개선 프롬프트

이 시스템의 핵심은 '자동 학습'입니다. 아래 프롬프트는 일주일간의 예측 성공 및 실패 데이터를 바탕으로, 시스템의 약점을 진단하고, 분석 프롬프트를 스스로 개선하도록 유도하는 '메타 분석' 역할을 수행합니다. 이 보고서는 매주 월요일 오전에 생성되도록 설정할 수 있습니다.

```python
def get_weekly_feedback_and_prompt_improvement_prompt(failed_predictions, successful_predictions):
    # failed_predictions와 successful_predictions는 Notion '예측 검증 로그'에서 가져온 데이터 리스트입니다.
    # 예: [{"ticker": "TSLA", "prediction": "Bullish", "actual_change": -2.5, "reason": "Macroeconomic fears overshadowed product news."}]

    return f'''
    You are a Principal Analyst at Bridgewater Associates, specializing in quantitative analysis and model improvement.
    Your task is to analyze the performance of a junior AI analyst over the past week and provide a concrete, actionable plan to improve its accuracy.

    ### Past Week's Performance Summary:

    #### Failed Predictions:
    {str(failed_predictions)}

    #### Successful Predictions:
    {str(successful_predictions)}

    ### Your Task: Generate a Weekly Feedback Report

    Analyze the provided data and generate a report in the following JSON format. Do not add any text outside of the JSON object.

    **Instruction for `actionable_prompt_improvement`**: Only provide a suggestion if you identify a clear, systematic pattern of failure in the `root_cause_analysis_of_failures`. If the failures seem random, non-systematic, or if the accuracy is already high, set the value of `actionable_prompt_improvement` to `null`.

      "weekly_summary": {{
        "total_predictions": <int>,
        "correct_predictions": <int>,
        "accuracy_rate": "<float>%",
        "key_takeaway": "Provide a one-sentence summary in KOREAN of the main lesson learned this week."
      }},
      "root_cause_analysis_of_failures": [
        {{
          "theme": "Identify a recurring theme or pattern in the failures (e.g., 'Underestimation of Macro Factors', 'Overemphasis on Single News Event', 'Misinterpretation of Sector-wide Trends'). If no clear pattern, state so.",
          "supporting_examples": ["List ticker symbols of failed predictions that support this theme."],
          "detailed_analysis": "Explain in KOREAN the underlying reason for this pattern of failure. Why did the model make these mistakes?"
        }}
      ],
      "analysis_of_successes": {{
        "common_pattern": "What is the common pattern or type of analysis that led to successful predictions? Explain in KOREAN. (e.g., 'Accurate analysis of earnings reports', 'Correctly identifying M&A impacts').",
        "supporting_examples": ["List ticker symbols of successful predictions."]
      }},
      "actionable_prompt_improvement": {{ // This entire object should be null if no improvement is needed.
        "problem_statement": "Based on the root cause analysis, what is the core weakness of the current analysis prompt? Explain in KOREAN.",
        "suggested_improvement_to_prompt": "Provide a specific, revised section for the original prompt to address this weakness. For example, suggest adding a new analysis step or a new field to the JSON output. This should be a concrete block of text that can be copied and pasted.",
        "expected_outcome": "How will this change improve future analysis accuracy? Explain in KOREAN."
      }}
    '''
```

## 6. 최종 구현: Python 스크립트 (`optimized_market_mover.py`)

-   **정보 소스 변경**: `NewsAPI` 대신 `feedparser`를 사용하여 주요 금융 뉴스 사이트의 RSS 피드를 가져옵니다.
-   **피드백 로직 추가**:
    1.  (어제 실행분) Notion에서 "Positive" 또는 "Negative"로 분석된 종목과 그 요약을 파일(`previous_analysis.json`)로 저장합니다.
    2.  (오늘 실행분) `yfinance`로 해당 종목의 실제 주가 변동을 확인합니다.
    3.  예상과 달랐다면, 어제 분석 요약과 새로운 뉴스를 함께 `get_self_improving_analysis_prompt`에 넣어 '피드백 분석'을 요청합니다.
    4.  결과를 Notion의 `피드백 분석` 필드에 업데이트합니다.
-   **양방향 분석**: `sentiment`가 "Positive" 또는 "Negative"이고 `conviction_score`가 높은 경우 모두 Notion에 저장합니다.

*(세부적인 Python 코드 구현은 `optimized_market_mover.py` 파일을 참고하세요. 이 가이드에서는 개념과 로직 흐름에 집중합니다.)*

## 6. 자동화: GitHub Actions 설정

-   **Cron 스케줄**: 하루에 두 번 실행되도록 설정할 수 있습니다.
    -   **오전 (시장 마감 후)**: 전날 분석에 대한 피드백 생성 및 저장
    -   **오후 (시장 개장 전)**: 당일 시장에 영향을 줄 새로운 뉴스 분석
-   **Secret 관리**: `.env` 파일의 내용을 GitHub Repository Secrets에 동일하게 등록합니다.

```yaml
# .github/workflows/market_analysis.yml
name: Self-Improving Market Analysis

on:
  workflow_dispatch:
  schedule:
    - cron: '0 1 * * *'   # 매일 UTC 01:00 (한국 오전 10시): 피드백 분석 실행
    - cron: '0 22 * * *'  # 매일 UTC 22:00 (한국 오전 7시): 신규 뉴스 분석 실행

jobs:
  analyze-market:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Analysis Script
        env:
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python optimized_market_mover.py
```

## 7. 매우 중요한 주의사항

**이 시스템은 금융 투자 조언이 아닙니다.** AI의 분석과 피드백은 불완전하며, 언제나 예상치 못한 시장 변수가 존재합니다. 이 도구는 투자 아이디어를 발굴하고 분석 능력을 키우는 **'보조 도구'**로만 활용해야 합니다. 모든 투자 결정과 책임은 투자자 본인에게 있습니다.

## 8. 결론

이제 당신은 단순히 정보를 수집하는 것을 넘어, 스스로 학습하고 발전하는 AI 금융 어시스턴트를 갖게 되었습니다. 매일 아침 Notion 대시보드에서 새로운 투자 아이디어와 함께, 어제의 분석에 대한 AI의 자기 반성까지 확인하며 시장을 더 깊이 있게 이해하는 경험을 시작해보세요.