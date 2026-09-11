# PIUM AI

대학 특허 · 연구성과 · 기술이전 · 기술사업화 분야를 위한 Streamlit 챗봇입니다.

## 데이터 구조

PIUM AI의 대학정보공시 통계는 이제 **Supabase 저장본 우선**으로 동작합니다.

1. 대학정보공시 API에는 연도(`exmnYr`)만 전달합니다.
2. 해당 연도의 전체 대학 특허/기술이전 데이터를 받아 Supabase에 저장합니다.
3. 일반 사용자 질문은 대학정보공시 API를 다시 호출하지 않고 Supabase 데이터를 즉시 조회합니다.
4. 앱 시작 시 기본 연도 범위에서 아직 동기화되지 않은 연도만 자동 수집할 수 있습니다.
5. 기존 행은 기본 동기화에서 덮어쓰지 않습니다.
6. 관리자가 명시적으로 선택한 경우에만 특정 연도를 전체 재동기화합니다.

특허와 기술이전은 원천 API가 다르므로 Supabase에서도 별도 테이블로 보관하고, 두 지표를 함께 분석할 때 Python에서 학교명·분교여부·연도를 기준으로 병합합니다.

## Supabase 최초 설정

1. Supabase 프로젝트를 만듭니다.
2. SQL Editor에서 저장소의 `supabase_schema.sql`을 1회 실행합니다.
3. Streamlit Secrets에 Project URL과 서버용 Secret Key를 입력합니다.

현재 Supabase는 서버/백엔드 용도로 `sb_secret_...` 형식의 Secret Key 사용을 권장합니다. 이 키는 GitHub 코드에 넣지 말고 Streamlit Secrets에만 저장하세요.

## Streamlit Secrets

```toml
OPENAI_API_KEY = "sk-..."

# 교육데이터플랫폼 공통 인증키
EDMGR_API_KEY = "..."
EDMGR_PATENT_API_URL = "https://openapi.edmgr.kr/openAPI/service/SA00202500062"
EDMGR_TRANSFER_API_URL = "https://openapi.edmgr.kr/openAPI/service/SA00202500061"
EDMGR_AUTH_MODE = "header"

# Supabase - 반드시 서버용 Secret Key 사용
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_..."

# 관리자 동기화 화면 보호용. 원하는 비밀번호를 직접 지정
ADMIN_SYNC_PASSWORD = "..."

# 기본 통계/동기화 범위
DEFAULT_YEAR = "2025"
SYNC_DEFAULT_YEAR_COUNT = "5"
AUTO_SYNC_EDMGR = "true"

# 선택
KIPRIS_API_KEY = "..."

OPENAI_MODEL = "gpt-5.6-luna"
OPENAI_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "coral"
```

`SYNC_DEFAULT_YEAR_COUNT=5`는 앱 시작 시 확인할 기본 범위일 뿐입니다. 관리자는 사이드바에서 시작/종료 연도를 직접 바꿔 원하는 범위를 최초 일괄 적재할 수 있습니다.

`AUTO_SYNC_EDMGR=true`이면 Streamlit 서버가 새로 시작될 때 `university_disclosure_sync`를 확인해 **아직 완료되지 않은 연도만** 대학정보공시 API에서 가져옵니다. 이미 동기화 완료된 연도는 API를 다시 호출하지 않습니다.

## Supabase 테이블

- `university_patent_stats`: 연도별·대학별 특허 출원/등록 실적
- `university_transfer_stats`: 연도별·대학별 기술이전 계약/수입료 실적
- `university_disclosure_sync`: 특허/기술이전별 동기화 완료 연도 기록

각 통계 테이블은 `(school_name, branch_yn, year)`를 기본키로 사용합니다. 따라서 일반 **신규 데이터 동기화**에서는 이미 존재하는 대학·연도 행을 덮어쓰지 않고 없는 행만 INSERT합니다.

## 관리자 동기화

사이드바에서 `ADMIN_SYNC_PASSWORD`를 입력하면 다음 기능이 나타납니다.

- **신규 데이터만 동기화**: 이미 동기화 완료된 연도는 건너뛰고, 없는 연도/행만 추가
- **선택 연도 전체 재동기화**: 확인 체크 후 기존 행도 대학정보공시 최신 값으로 UPSERT

일반 사용자가 챗봇에서 통계 질문을 할 때는 Supabase만 읽으므로 대학정보공시 API 호출량이 증가하지 않습니다.

## 주요 기능

- GPT-5.6 Luna 기반 대화형 질의
- Supabase 기반 대학 특허/기술이전 통계 즉시 조회
- OpenAI Web Search 기반 최신 정보 탐색
- Google Patents 우선 특허·선행기술·관련 문헌 탐색
- KIPRIS Plus 선택 호출
- 모바일 반응형 UI
- 스마트폰/PC 마이크 음성 질문
- 선택형 TTS 답변 재생
- 표·차트·Excel 다운로드

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 데이터 사용 원칙

- 대학정보공시 통계 숫자는 대학정보공시 API에서 수집해 Supabase에 저장한 값만 사용합니다.
- 일반 통계 질의는 Supabase 저장본만 읽습니다.
- 대학정보공시 API는 최초 적재, 신규 연도 동기화, 관리자 전체 재동기화에만 사용합니다.
- Google Patents/Web Search는 탐색·동향·관련 특허/문헌에 사용합니다.
- KIPRIS Plus는 정확한 한국 특허 공식 확인에 우선 사용합니다.
- 서비스 범위를 벗어난 질문은 차단합니다.
