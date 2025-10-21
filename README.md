# Automatic FinanceNews 📈

매일 자동으로 시장 뉴스를 분석하고 Notion에 인사이트를 기록하는 시스템입니다.

## 🔒 보안 주의사항

**절대 `.env` 파일을 Git에 올리지 마세요!**

- `.env` 파일은 `.gitignore`에 포함되어 있어 실수로 커밋되는 것을 방지합니다.
- `.env.example` 파일을 복사하여 본인의 API 키와 데이터베이스 ID를 입력하세요.

## 📋 설정 방법

1.  **`.env` 파일 생성**

    - `.env.example` 파일을 `.env`로 복사합니다.

2.  **환경 변수 입력**

    - `.env` 파일을 열고 본인의 API 키와 3개의 Notion 데이터베이스 ID를 입력합니다.
    - `NOTION_API_KEY`, `GEMINI_API_KEY`, `NOTION_DATABASE_ID`, `NOTION_FEEDBACK_DB_ID`, `NOTION_REPORT_DB_ID`

3.  **패키지 설치**

    ```bash
    pip install -r requirements.txt
    ```

4.  **스크립트 실행**
    ```bash
    python advanced_market_analyzer.py
    ```

## 🚀 GitHub Actions 자동화

이 프로젝트는 `.github/workflows/market_analysis.yml`에 정의된 워크플로우에 따라 매일 자동으로 실행되도록 설정할 수 있습니다.

## 📝 파일 설명

- `advanced_market_analyzer.py`: 메인 실행 파일. 모든 분석, 피드백, 저장 로직을 포함합니다.
- `Market_Mover_Discovery_Assistant_Guide.md`: 시스템의 상세 설계 및 AI 프롬프트 가이드 문서입니다.
- `SETUP_GUIDE.md`: 3개의 Notion 데이터베이스 생성 방법을 포함한 상세 설치 가이드입니다.
- `.env.example`: 필요한 환경변수 목록을 보여주는 예시 파일입니다.
- `requirements.txt`: 실행에 필요한 Python 패키지 목록입니다.
- `.github/workflows/market_analysis.yml`: GitHub Actions 자동화 워크플로우 파일입니다.
