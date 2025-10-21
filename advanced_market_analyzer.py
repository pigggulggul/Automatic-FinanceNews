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
gemini_model = genai.GenerativeModel('gemini-pro-latest')

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
    You are a top-tier analyst at Goldman Sachs. Your task is to analyze a batch of news articles and return a JSON array where each object represents the analysis for one article.
    ### Articles to Analyze:
    {''.join(article_inputs)}
    ### Analysis Instructions:
    Each JSON object must follow this format:
    {{
      "article_index": <int>,
      "korean_title": "Translate the original article title to KOREAN.",
      "mentioned_tickers": ["AAPL", "MSFT"],
      "directionality": "Bullish|Bearish|Mixed. Based on the overall analysis.",
      "market_impact": "High|Medium|Low. Estimate the potential market impact.",
      "key_drivers": "List key positive drivers in KOREAN.",
      "risk_factors": "List key risk factors in KOREAN.",
      "price_catalyst": "Describe the primary price catalyst in KOREAN.",
      "summary": "Summarize in KOREAN (3-4 sentences).",
      "sentiment": "Positive|Negative|Neutral",
      "news_category": "Earnings|Product Launch|M&A|Partnership|Regulatory|Macroeconomic|Executive Change|Other",
      "impact_analysis": "Analyze short-term impact in KOREAN.",
      "conviction_score": 8
    }}
    Return ONLY the JSON array.
    '''

def get_weekly_feedback_and_prompt_improvement_prompt(failed_predictions, successful_predictions):
    return f'''
    You are a Principal Analyst. Analyze the performance of a junior AI analyst and provide a concrete plan to improve its accuracy.
    ### Past Week's Performance Summary:
    #### Failed Predictions: {str(failed_predictions)}
    #### Successful Predictions: {str(successful_predictions)}
    ### Your Task: Generate a Weekly Feedback Report
    Analyze the data and generate a report in JSON format. **Instruction for `actionable_prompt_improvement`**: Only provide a suggestion if you identify a clear, systematic pattern of failure. If failures seem random or accuracy is high, set `actionable_prompt_improvement` to `null`.
    {{
      "weekly_summary": {{"total_predictions": {len(failed_predictions) + len(successful_predictions)}, "correct_predictions": {len(successful_predictions)}, "accuracy_rate": "{ (len(successful_predictions) / (len(failed_predictions) + len(successful_predictions))) * 100 if (len(failed_predictions) + len(successful_predictions)) > 0 else 0:.1f}%", "key_takeaway": "Provide a one-sentence summary in KOREAN."}},
      "root_cause_analysis_of_failures": [{{"theme": "Identify a recurring theme in failures.", "supporting_examples": ["TSLA", "GOOG"], "detailed_analysis": "Explain the reason in KOREAN."}}],
      "analysis_of_successes": {{"common_pattern": "What is the common pattern in successes? Explain in KOREAN.", "supporting_examples": ["NVDA"]}},
      "actionable_prompt_improvement": {{"problem_statement": "What is the core weakness? Explain in KOREAN.", "suggested_improvement_to_prompt": "Provide a specific, revised section for the original prompt.", "expected_outcome": "How will this improve accuracy? Explain in KOREAN."}}
    }}
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
        if not result.get("mentioned_tickers") or result.get("conviction_score", 0) < 6:
            continue
        
        article = result.get('original_article', {})
        properties = {
            "기사 제목": {"title": [{"text": {"content": result.get("korean_title", article.get('title', 'N/A'))}}]}, 
            "언급된 종목": {"rich_text": [{"text": {"content": ", ".join(result.get("mentioned_tickers", []))}}]}, 
            "방향성": {"select": {"name": result.get("directionality", "Mixed")}} if result.get("directionality") else None,
            "시장 영향도": {"select": {"name": result.get("market_impact", "Low")}} if result.get("market_impact") else None,
            "핵심 동인": {"rich_text": [{"text": {"content": result.get("key_drivers", "")}}]},
            "리스크 요인": {"rich_text": [{"text": {"content": result.get("risk_factors", "")}}]},
            "가격 촉매": {"rich_text": [{"text": {"content": result.get("price_catalyst", "")}}]},
            "AI 확신 점수": {"number": result.get("conviction_score")},
            "AI 분석 요약": {"rich_text": [{"text": {"content": result.get("summary", "")}}]},
            "뉴스 카테고리": {"select": {"name": result.get("category", "Other")}} if result.get("category") else None,
            "감성분석": {"select": {"name": result.get("sentiment", "Neutral")}} if result.get("sentiment") else None,
            "URL": {"url": article.get('link')}
        }
        # None 값인 속성 제거
        properties = {k: v for k, v in properties.items() if v is not None}

        children = [
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "AI 상세 분석"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": result.get("impact_analysis", "N/A")}}]}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "기사 원문 요약"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": article.get('summary', 'N/A')}}]}}
        ]

        try:
            notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=properties, children=children)
            api_call_counter['notion'] += 1
            count += 1
        except APIResponseError as e:
            print(f"✗ Notion 저장 오류: {result.get('korean_title', '')} - {e}")
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
                
                if not tickers_text or predicted_sentiment not in ["Positive", "Negative"]:
                    continue

                ticker = tickers_text.split(",")[0].strip()
                stock = yf.Ticker(ticker)
                hist = stock.history(period="2d")
                
                if len(hist) < 2:
                    continue

                actual_change = (hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100
                
                correct = (predicted_sentiment == "Positive" and actual_change > 0) or (predicted_sentiment == "Negative" and actual_change < 0)
                
                feedback_properties = {
                    "종목": {"title": [{"text": {"content": ticker}}]},
                    "예측 방향": {"select": {"name": predicted_sentiment}},
                    "실제 변동": {"number": round(actual_change, 2)},
                    "예측 정확": {"checkbox": bool(correct)}, # numpy.bool_를 표준 bool로 변환
                    "원인 분석": {"rich_text": [{"text": {"content": "성공: 예측과 실제 움직임 일치" if correct else "실패: 예측과 실제 움직임 불일치"}}]}
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
                "reason": props.get("원인 분석", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
            }
            if props.get("예측 정확", {}).get("checkbox"):
                successful_predictions.append(prediction)
            else:
                failed_predictions.append(prediction)
        
        print(f"  - 지난 주 예측 결과: {len(successful_predictions)}개 성공, {len(failed_predictions)}개 실패")
        
        prompt = get_weekly_feedback_and_prompt_improvement_prompt(failed_predictions, successful_predictions)
        response = gemini_model.generate_content(prompt)
        api_call_counter['gemini'] += 1
        print("    - Gemini API 호출 완료. 30초 대기...")
        time.sleep(30)
        
        json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        report_data = json.loads(json_text)

        if report_data.get("actionable_prompt_improvement"):
            print("  - 프롬프트 개선안이 발견되었습니다. 보고서를 생성합니다.")
            
            report_title = f"주간 피드백 보고서 ({datetime.now().strftime('%Y년 %m월 %d일')})"
            summary = report_data.get("weekly_summary", {})
            root_cause = report_data.get("root_cause_analysis_of_failures", [{}])[0]
            success_analysis = report_data.get("analysis_of_successes", {})
            improvement = report_data.get("actionable_prompt_improvement", {})

            properties = {
                "보고서 기간": {"title": [{"text": {"content": report_title}}],
                "정확도": {"rich_text": [{"text": {"content": summary.get("accuracy_rate", "N/A")}}]},
                "핵심 요약": {"rich_text": [{"text": {"content": summary.get("key_takeaway", "N/A")}}]},
                "실패 원인 분석": {"rich_text": [{"text": {"content": f"테마: {root_cause.get('theme')}\n분석: {root_cause.get('detailed_analysis')}"}}]},
                "성공 비결 분석": {"rich_text": [{"text": {"content": success_analysis.get("common_pattern", "N/A")}}]},
                "개선된 프롬프트 제안": {"rich_text": [{"text": {"content": improvement.get("suggested_improvement_to_prompt", "N/A")}}]}}
            }
            notion.pages.create(parent={"database_id": NOTION_REPORT_DB_ID}, properties=properties)
            api_call_counter['notion'] += 1
            print(f"✓ 주간 피드백 보고서를 Notion에 저장했습니다.")
        else:
            print("  - 특별한 실패 패턴이 없어, 프롬프트 개선 제안 없이 보고를 생략합니다.")

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
