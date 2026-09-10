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

# 대학정보공시 OpenAPI는 서비스별 발급키를 각각 입력
EDMGR_PATENT_API_KEY = "..."   # 특허출원및등록실적 SA00202500062
EDMGR_TRANSFER_API_KEY = "..." # 기술이전수입료및계약실적 SA00202500061

KIPRIS_API_KEY = "..." # 선택: 없어도 앱은 실행되며 Google Patents 웹검색으로 fallback

OPENAI_MODEL = "gpt-5.6-luna"
OPENAI_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "coral"
EDMGR_AUTH_MODE = "header"
DEFAULT_YEAR = "2025"
```

`KIPRIS_API_KEY`가 없으면 KIPRIS route가 필요한 질문도 앱이 중단되지 않고 Google Patents 웹검색으로 대체합니다.

기존 테스트 배포에서 `EDMGR_API_KEY` 하나를 사용하고 있었다면 하위 호환 fallback으로는 동작하지만, 실제 운영에서는 위의 두 서비스별 키를 각각 입력하는 것을 권장합니다.

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
