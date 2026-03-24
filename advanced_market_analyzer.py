import os
import json
import feedparser
import yfinance as yf
from datetime import datetime, timedelta
from notion_client import Client, APIResponseError
from dotenv import load_dotenv
import google.generativeai as genai
import time

# --- 1. 설정 및 초기화 ---
print("=" * 60)
print("고급 시장 분석 시스템 초기화...")
print("=" * 60)

load_dotenv()

# API 키 및 ID 로드
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_FEEDBACK_DB_ID = os.getenv("NOTION_FEEDBACK_DB_ID")
NOTION_REPORT_DB_ID = os.getenv("NOTION_REPORT_DB_ID")

# API 호출 횟수 카운터
api_call_counter = {'gemini': 0, 'notion': 0}

# 유효성 검사
if not all([NOTION_API_KEY, GEMINI_API_KEY, NOTION_DATABASE_ID, NOTION_FEEDBACK_DB_ID, NOTION_REPORT_DB_ID]):
    raise ValueError("하나 이상의 필수 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")

# 클라이언트 초기화
notion = Client(auth=NOTION_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# RSS 피드 소스
RSS_FEEDS = {
    "Yahoo Finance": "https://finance.yahoo.com/rss/topstories",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/topstories/",
    "Seeking Alpha": "https://seekingalpha.com/feed.xml"
}

# --- 2. 프롬프트 정의 ---
def get_batch_analysis_prompt(articles):
    article_inputs = []
    for i, article in enumerate(articles):
        article_inputs.append(f"<article index=\"{i}\"><title>{article['title']}</title><content>{article['summary']}</content></article>")
    
    return f'''
    You are a senior equity analyst at a top-tier investment firm. Your job is to analyze news and predict short-term stock price movements with high accuracy.

    ### News Articles:
    {''.join(article_inputs)}

    ### Analysis Framework:
    For each article, perform this structured analysis:

    1. **Materiality Check**: Does this news contain concrete, actionable information? Skip generic/rehashed content.

    2. **Causal Analysis**:
        - What specific event occurred? (earnings beat/miss, product launch, etc.)
        - What is the magnitude? (revenue numbers, user growth %)
        - What is the market expectation vs. reality gap?

    3. **Pre-Mortem Analysis (CRITICAL STEP)**:
        - Form an initial prediction (Positive/Negative).
        - **Then, explicitly state the top 3 strongest arguments or risk factors for why your initial prediction might be WRONG.** This analysis will populate the `pre_mortem_risks` field.

    4. **Price Impact Logic & Final Sentiment**:
        - Bullish: Clear, positive catalyst (revenue beat, strategic win).
        - Bearish: Clear, negative catalyst (guidance cut, regulatory headwind).
        - **Neutral: [NEW RULE] Classify as 'Neutral' if the predicted change is marginal (e.g., within a +/- 0.5% range), if signals are mixed (e.g., revenue beat but guidance miss), or if there is no clear catalyst.**

    5. **Confidence Calibration**:
        - Based on your Pre-Mortem. If `pre_mortem_risks` are strong, confidence must be lower.
        - High (8-10): Clear catalyst + quantifiable impact + low-risk pre-mortem.
        - Medium (5-7): Important but lacks specifics, or pre-mortem identifies significant counter-arguments.
        - Low (1-4): Speculative, opinion-based, or high-risk pre-mortem.

    ### Output Format (JSON):
    {{
      "article_index": <int>,
      "korean_title": "기사 제목을 한글로 번역",
      "mentioned_tickers": ["AAPL", "MSFT"],
      "sentiment": "Positive|Negative|Neutral",
      "conviction_score": <1-10>,
      "summary": "한글로 3문장 분석:
        1) 핵심 사건: [구체적 수치/사실 포함]
        2) 주가 영향 논리: [왜 오르거나 내릴 것인가]
        3) 시간 프레임: [단기/중기 영향]",
      "pre_mortem_risks": "KOREAN: 이 예측이 틀릴 수 있는 가장 강력한 이유 3가지 (Pre-mortem 분석 결과)"
    }}

    ### Quality Standards:
    - ❌ Bad: "애플의 신제품 출시로 긍정적 전망"
    - ✅ Good (Example Output):
      {{
        "article_index": 0,
        "korean_title": "애플, 아이폰15 사전예약 전년 대비 20% 증가",
        "mentioned_tickers": ["AAPL"],
        "sentiment": "Positive",
        "conviction_score": 7,
        "summary": "1) 핵심 사건: 아이폰15 사전예약이 전년 대비 20% 증가하며 초기 수요 강세 확인.\n2) 주가 영향 논리: 단기 매출 기대감 상승으로 주가에 긍정적.\n3) 시간 프레임: 단기 (다음 분기 실적 발표 전)",
        "pre_mortem_risks": "1) 거시경제 위축으로 실제 판매 전환율이 낮을 수 있음.\n2) 높은 부품 비용으로 인해 마진이 압박받을 수 있음.\n3) 해당 뉴스가 이미 시장 기대치에 선반영되었을 가능성."
      }}

    ### Critical Rules:
    - Only analyze articles mentioning **specific publicly traded tickers**.
    - Distinguish between "company did X" (fact) vs. "analyst says X" (opinion).
    - **[NEW RULE] Your `conviction_score` MUST reflect your `pre_mortem_risks`. If `pre_mortem_risks` are significant, the score CANNOT be 9 or 10.**

    Return ONLY a valid JSON array. No explanations outside JSON.
    '''

def get_weekly_feedback_and_prompt_improvement_prompt(failed_predictions, successful_predictions):
    total = len(failed_predictions) + len(successful_predictions)
    accuracy = (len(successful_predictions) / total * 100) if total > 0 else 0

    return f'''
    You are an AI performance auditor. Analyze prediction accuracy and suggest improvements.

    ### Performance Data:
    - **Failed Predictions (with pre-mortem)**: 
      - Each object shows the prediction that failed, and the `pre_mortem` analysis the AI wrote *before* it failed.
      - {str(failed_predictions)}
    - **Successful Predictions**: {str(successful_predictions)}
    - **Accuracy**: {accuracy:.1f}%

    ### Your Task:
    Analyze patterns and generate a JSON report. Only suggest improvements if you find **systematic, recurring failures**.

    **CRITICAL ANALYSIS for `failure_analysis`**:
    For each failure, check its `pre_mortem` field.
    1.  **"Ignored Risk"**: Did the AI correctly identify the risk in its `pre_mortem` but still make the wrong call (e.g., high conviction)?
    2.  **"Missed Risk"**: Was the failure caused by a risk the AI completely failed to identify in its `pre_mortem`?
    Your root cause analysis MUST differentiate between these two failure types.

    **JSON Format:**
    {{
      "weekly_summary": {{
        "total_predictions": {total},
        "correct_predictions": {len(successful_predictions)},
        "accuracy_rate": "{accuracy:.1f}%",
        "key_takeaway": "One-sentence summary in KOREAN"
      }},
      "failure_analysis": {{
        "recurring_theme": "What common mistake pattern exists? (e.g., 'Ignored Risk', 'Missed Risk') (KOREAN)",
        "examples": ["TSLA", "AAPL"],
        "root_cause": "Why did the AI fail? Did it ignore its own pre-mortem? (KOREAN)"
      }},
      "success_analysis": {{
        "common_pattern": "What makes successful predictions accurate? (KOREAN)",
        "examples": ["NVDA"]
      }},
      "actionable_improvement": {{
        "needed": true/false,
        "problem": "Core weakness if systematic failure exists (KOREAN)",
        "solution": "Specific prompt modification suggestion",
        "expected_impact": "How this will improve accuracy (KOREAN)"
      }}
    }}

    **Important**: Set "needed": false if accuracy > 70% or failures are random.
    Return ONLY the JSON object.
    '''

# --- 3. 핵심 기능 함수 ---
def check_notion_connections():
    print("\n[단계 1/6] Notion 데이터베이스 연결 확인 중...")
    db_map = {
        "메인 분석 DB": NOTION_DATABASE_ID,
        "일일 피드백 DB": NOTION_FEEDBACK_DB_ID,
        "주간 보고서 DB": NOTION_REPORT_DB_ID
    }
    all_connected = True
    for name, db_id in db_map.items():
        try:
            notion.databases.retrieve(database_id=db_id)
            api_call_counter['notion'] += 1
            print(f"  ✓ {name}: 연결 성공")
        except APIResponseError as e:
            print(f"  ✗ {name}: 연결 실패! .env 파일의 ID가 정확한지, Notion에서 통합 권한을 부여했는지 확인하세요.")
            print(f"    오류: {e}")
            all_connected = False
    if not all_connected:
        raise ConnectionError("Notion 데이터베이스에 연결할 수 없습니다. 스크립트를 종료합니다.")
    print("모든 Notion 데이터베이스가 성공적으로 연결되었습니다.")

def fetch_news_from_rss(feeds):
    print("\n[단계 2/6] RSS 피드에서 최신 뉴스 수집 중...")
    articles = []
    for name, url in feeds.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                articles.append({
                    'source': name,
                    'title': entry.title,
                    'link': entry.link,
                    'summary': entry.get('summary', ''),
                    'published': entry.get('published', datetime.now().isoformat())
                })
            print(f"  ✓ {name}: {len(feed.entries[:10])}개 수집")
        except Exception as e:
            print(f"  ✗ {name} 수집 실패: {e}")
    print(f"총 {len(articles)}개의 기사를 수집했습니다.")
    return articles

def analyze_articles_in_batch(articles, batch_size=4):
    print("\n[단계 3/6] Gemini 배치 분석 시작 (분당 2회 제한 준수)...")
    all_results = []
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i+batch_size]
        print(f"  - 배치 {i//batch_size + 1}: {len(batch)}개 기사 분석 요청...")
        try:
            prompt = get_batch_analysis_prompt(batch)
            response = gemini_model.generate_content(prompt)
            api_call_counter['gemini'] += 1
            print("    - Gemini API 호출 완료. 30초 대기...")
            time.sleep(30)

            json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            batch_results = json.loads(json_text)
            
            for result in batch_results:
                article_index = result.get("article_index")
                if article_index is not None and 0 <= article_index < len(batch):
                    result['original_article'] = batch[article_index]
            
            all_results.extend(batch_results)
        except Exception as e:
            print(f"  ✗ 배치 {i//batch_size + 1} 분석 실패: {e}")
    print(f"총 {len(all_results)}개의 분석 결과를 얻었습니다.")
    return all_results

def save_analysis_to_notion(analysis_results):
    print("\n[단계 4/6] Notion에 분석 결과 저장 중...")
    count = 0
    for result in analysis_results:
        # 필터링: 종목이 없거나 확신도가 6 미만인 경우 제외
        if not result.get("mentioned_tickers") or result.get("conviction_score", 0) < 6:
            continue

        article = result.get('original_article', {})

        # [!] "AI Pre-mortem" 속성 추가 (Notion DB에 해당 속성이 있어야 함)
        properties = {
            "기사 제목": {"title": [{"text": {"content": result.get("korean_title", article.get('title', 'N/A'))}}]},
            "언급된 종목": {"rich_text": [{"text": {"content": ", ".join(result.get("mentioned_tickers", []))}}]},
            "감성분석": {"select": {"name": result.get("sentiment", "Neutral")}},
            "AI 확신 점수": {"number": result.get("conviction_score", 0)},
            "AI 분석 요약": {"rich_text": [{"text": {"content": result.get("summary", "")}}]},
            "AI Pre-mortem": {"rich_text": [{"text": {"content": result.get("pre_mortem_risks", "")}}]} ,
            "URL": {"url": article.get('link', "")}
        }

        # 페이지 본문에 원문 요약 추가
        children = [
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "📰 기사 원문 요약"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": article.get('summary', 'N/A')[:2000]}}]}}  # Notion 2000자 제한
        ]

        try:
            notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=properties, children=children)
            api_call_counter['notion'] += 1
            count += 1
            print(f"  ✓ 저장: {result.get('korean_title', 'N/A')[:30]}... (확신도: {result.get('conviction_score')})")
        except APIResponseError as e:
            print(f"  ✗ Notion 저장 오류: {result.get('korean_title', '')} - {e}")

    print(f"✓ 총 {count}개의 유의미한 분석을 Notion에 저장했습니다.")

    
def run_daily_feedback_check():
    print("\n[단계 5/6] 일일 피드백 검증 시작...")
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    try:
        response = notion.databases.query(database_id=NOTION_DATABASE_ID, filter={"timestamp": "created_time", "created_time": {"on_or_after": yesterday}})
        api_call_counter['notion'] += 1
        predictions = response.get("results", [])
        if not predictions:
            print("  - 검증할 어제 예측이 없습니다.")
            return

        print(f"  - {len(predictions)}개의 어제 예측을 검증합니다.")
        for page in predictions:
            try:
                props = page.get("properties", {})
                tickers_text = props.get("언급된 종목", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
                predicted_sentiment = props.get("감성분석", {}).get("select", {}).get("name")
                
                # [!] 원본 Pre-mortem 텍스트 읽어오기
                pre_mortem_text = props.get("AI Pre-mortem", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
                
                if not tickers_text or predicted_sentiment not in ["Positive", "Negative"]:
                    continue

                ticker = tickers_text.split(",")[0].strip()
                stock = yf.Ticker(ticker)
                hist = stock.history(period="2d")
                
                if len(hist) < 2:
                    continue

                actual_change = (hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100
                
                correct = (predicted_sentiment == "Positive" and actual_change > 0) or (predicted_sentiment == "Negative" and actual_change < 0)
                
                # [!] "Pre-mortem 원본" 속성 추가 (피드백 DB에 해당 속성이 있어야 함)
                feedback_properties = {
                    "종목": {"title": [{"text": {"content": ticker}}]},
                    "예측 방향": {"select": {"name": predicted_sentiment}},
                    "실제 변동": {"number": round(actual_change, 2)},
                    "예측 정확": {"checkbox": bool(correct)}, # numpy.bool_를 표준 bool로 변환
                    "원인 분석": {"rich_text": [{"text": {"content": "성공: 예측과 실제 움직임 일치" if correct else "실패: 예측과 실제 움직임 불일치"}}]},
                    "Pre-mortem 원본": {"rich_text": [{"text": {"content": pre_mortem_text}}]} # [!] Pre-mortem 데이터 복사
                }
                notion.pages.create(parent={"database_id": NOTION_FEEDBACK_DB_ID}, properties=feedback_properties)
                api_call_counter['notion'] += 1
                print(f"  ✓ 피드백 저장: {ticker} (예측: {predicted_sentiment}, 실제: {actual_change:.2f}%) -> {'성공' if correct else '실패'}")
            except Exception as e:
                print(f"  ✗ 피드백 처리 오류: {e}")
    except APIResponseError as e:
        print(f"✗ 어제 분석 데이터 조회 실패: {e}")

def run_weekly_report_generation():
    print("\n[추가 작업] 주간 피드백 보고서 생성 시작...")
    last_week = (datetime.now() - timedelta(days=7)).isoformat()
    try:
        response = notion.databases.query(database_id=NOTION_FEEDBACK_DB_ID, filter={"timestamp": "created_time", "created_time": {"on_or_after": last_week}})
        api_call_counter['notion'] += 1
        feedback_logs = response.get("results", [])
        if not feedback_logs:
            print("  - 분석할 피드백 로그가 없습니다.")
            return

        successful_predictions = []
        failed_predictions = []
        for page in feedback_logs:
            props = page.get("properties", {})
            prediction = {
                "ticker": props.get("종목", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                "prediction": props.get("예측 방향", {}).get("select", {}).get("name"),
                "actual_change": props.get("실제 변동", {}).get("number"),
                "reason": props.get("원인 분석", {}).get("rich_text", [{}])[0].get("text", {}).get("content", ""),
                "pre_mortem": props.get("Pre-mortem 원본", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "") # [!] Pre-mortem 데이터 추가
            }
            if props.get("예측 정확", {}).get("checkbox"):
                successful_predictions.append(prediction)
            else:
                failed_predictions.append(prediction)
        
        print(f"  - 지난 주 예측 결과: {len(successful_predictions)}개 성공, {len(failed_predictions)}개 실패")
        
        # 데이터가 없으면 리포트 생성 스킵
        if not successful_predictions and not failed_predictions:
            print("  - 분석할 피드백 데이터가 충분하지 않습니다. 리포트를 건너뜁니다.")
            return

        prompt = get_weekly_feedback_and_prompt_improvement_prompt(failed_predictions, successful_predictions)
        response = gemini_model.generate_content(prompt)
        api_call_counter['gemini'] += 1
        print("    - Gemini API 호출 완료. 30초 대기...")
        time.sleep(30)

        json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        report_data = json.loads(json_text)

        # 개선이 필요한 경우에만 보고서 생성
        improvement = report_data.get("actionable_improvement", {})
        if improvement.get("needed"):
            print("  - 시스템적 실패 패턴 발견. 보고서를 생성합니다.")

            report_title = f"주간 피드백 보고서 ({datetime.now().strftime('%Y년 %m월 %d일')})"
            summary = report_data.get("weekly_summary", {})
            failure = report_data.get("failure_analysis", {})
            success = report_data.get("success_analysis", {})

            properties = {
                "보고서 기간": {"title": [{"text": {"content": report_title}}]},
                "정확도": {"rich_text": [{"text": {"content": summary.get("accuracy_rate", "N/A")}}]},
                "핵심 요약": {"rich_text": [{"text": {"content": summary.get("key_takeaway", "N/A")}}]},
                "실패 원인 분석": {"rich_text": [{"text": {"content": f"테마: {failure.get('recurring_theme', 'N/A')}\n근본 원인: {failure.get('root_cause', 'N/A')}"}}]},
                "성공 비결 분석": {"rich_text": [{"text": {"content": success.get("common_pattern", "N/A")}}]},
                "개선된 프롬프트 제안": {"rich_text": [{"text": {"content": improvement.get("solution", "N/A")}}]}
            }
            notion.pages.create(parent={"database_id": NOTION_REPORT_DB_ID}, properties=properties)
            api_call_counter['notion'] += 1
            print(f"✓ 주간 피드백 보고서를 Notion에 저장했습니다.")
        else:
            print("  - 정확도가 양호하거나 실패가 무작위적입니다. 보고서 생성을 생략합니다.")

    except Exception as e:
        print(f"  ✗ 주간 보고서 생성 실패: {e}")

# --- 9. 메인 실행 로직 ---
def main():
    try:
        check_notion_connections()
        
        # 월요일에만 주간 보고서 생성
        if datetime.now().weekday() == 0:
            run_weekly_report_generation()

        # 매일 실행되는 분석 및 피드백
        run_daily_feedback_check()
        articles = fetch_news_from_rss(RSS_FEEDS)
        if articles:
            analysis_results = analyze_articles_in_batch(articles)
            if analysis_results:
                save_analysis_to_notion(analysis_results)
        
    except Exception as e:
        print(f"\n스크립트 실행 중 심각한 오류 발생: {e}")
    finally:
        print("\n" + "=" * 60)
        print("모든 작업이 완료되었습니다.")
        print("API 호출 요약:")
        print(f"- Gemini: {api_call_counter['gemini']}회")
        print(f"- Notion: {api_call_counter['notion']}회")
        print(f"총 호출: {sum(api_call_counter.values())}회")
        print("=" * 60)

if __name__ == "__main__":
    main()
