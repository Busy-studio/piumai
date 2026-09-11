# PIUM AI

대학 특허 · 연구성과 · 기술이전 · 기술사업화 분야를 위한 Streamlit 챗봇입니다.

## 주요 기능

- GPT-5.6 Luna 기반 대화형 질의
- 대학정보공시 OpenAPI: 특허 출원/등록, 기술이전 계약/수입료 통계
- 질문별 필요한 대학정보공시 API만 호출
- OpenAI Web Search 기반 최신 정보 탐색
- Google Patents 우선 특허·선행기술·관련 문헌 탐색
- KIPRIS Plus: 정확한 국내 특허 확인이 필요한 경우에만 선택 호출
- 모바일 반응형 UI
- 스마트폰/PC 마이크 음성 질문
- 선택형 TTS 답변 재생
- 표·차트·Excel 다운로드

## Streamlit Secrets

Streamlit Cloud의 **App settings → Secrets**에 아래 값을 넣습니다.

```toml
OPENAI_API_KEY = "sk-..."

# 교육데이터플랫폼 공통 인증키
EDMGR_API_KEY = "..."

# 서비스별 End Point
EDMGR_PATENT_API_URL = "https://openapi.edmgr.kr/openAPI/service/SA00202500062"
EDMGR_TRANSFER_API_URL = "https://openapi.edmgr.kr/openAPI/service/SA00202500061"

KIPRIS_API_KEY = "..." # 선택: 없어도 앱은 실행되며 Google Patents 웹검색으로 fallback

OPENAI_MODEL = "gpt-5.6-luna"
OPENAI_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "coral"
EDMGR_AUTH_MODE = "header"
DEFAULT_YEAR = "2025"
```

### 교육데이터플랫폼 API 구조

- 특허출원및등록실적: `SA00202500062`
- 기술이전수입료및계약실적: `SA00202500061`
- 두 서비스는 동일한 `EDMGR_API_KEY`를 사용하고 End Point만 구분합니다.
- 기존의 `EDMGR_PATENT_API_KEY`, `EDMGR_TRANSFER_API_KEY`는 호환용 fallback으로만 남겨뒀습니다.
- `HTTP 404`와 `{"loc":"PROVIDER","message":"Not Found"}`가 함께 나오면 인증키가 전달된 뒤 provider 라우팅 단계에서 실패한 것이므로 승인정보의 End Point/서비스 활성화 상태를 확인합니다.
- 불필요한 인증방식 반복 호출은 제거했습니다. 기본은 `API_KEY` header + JSON POST입니다.

`KIPRIS_API_KEY`가 없으면 KIPRIS route가 필요한 질문도 앱이 중단되지 않고 Google Patents 웹검색으로 대체합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 데이터 사용 원칙

- 대학정보공시 통계 숫자는 OpenAPI 결과만 사용합니다.
- 특허 통계 질문은 특허출원및등록실적 API만, 기술이전 질문은 기술이전수입료및계약실적 API만 호출합니다.
- 두 지표의 상관/비교처럼 둘 다 필요한 질문에서만 두 API를 함께 호출합니다.
- Google Patents/Web Search는 탐색·동향·관련 특허/문헌에 사용합니다.
- KIPRIS Plus는 정확한 한국 특허 공식 확인에 우선 사용하며, 불필요한 호출을 줄이도록 라우팅합니다.
- 서비스 범위를 벗어난 질문은 차단합니다.
