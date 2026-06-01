# 📡 본심 대변인 「팡이」 통합 실행 계획서 (v4)

> 자동화 아키텍처 반영판 — I2V 제작(v3) + **감독형 자동화(슬랙 휴먼인더루프) 되살림**
> 벤치마크: 정서불안 김햄찌 (이미지 생성 + I2V 방식)
> MacBook Air M3 · 16GB · 작성일: 2026-05-30 / 최종수정: 2026-06-01

---

## 0. 무엇이 바뀌었나 (v3 → v4)

| 구분 | v3 | v4 |
| --- | --- | --- |
| 자동화 | "핵심은 수동, 주변부만 자동"으로 축소 | **감독형 자동화** — 생성·조립·전달은 자동, *판단만 슬랙으로* |
| 사람의 역할 | UI에서 손작업 | **슬랙에서 승인/재생성/수정** (폰으로 게이트 통과) |
| 인프라 | 거창한 파이프라인 보류 | **FastAPI + RQ + Postgres + Slack** 되살림 |
| 영상 생성 API | Kling 직접 API | **fal.ai 종량제** — Kling I2V 래핑, PyJWT 불필요 |
| 수정 | 명시 안 됨 | **수정 루프** — 피드백 → GPT 재작성 → 영향받는 컷만 재생성 |
| 핵심 원칙 | — | "자동이지만 게이트에서 사람이 거른다" |

> **왜 fal.ai로 바꿨나:** Kling 직접 API는 대량 구독제 기반이라 월 7~8편 규모엔 비효율적. fal.ai는 동일한 Kling I2V 모델을 종량제로 제공하고, SDK 한 줄로 비동기 처리까지 지원. 월 1~3만원 수준.

> **불변 철학:** 자동화 이전에 **수동 1편으로 품질부터 확정.** 사람은 "선별자·승인자"이지 "무한 생성기"가 아니다.

---

## 1. 하드웨어 — 가벼운 오케스트레이터 + 클라우드 생성

무거운 영상 생성은 **fal.ai 클라우드(Kling I2V)**가 대행. 로컬에 남는 건 *가벼운 오케스트레이터*(API 호출·작업상태 관리·슬랙 송수신)뿐이다.

| 항목 | 역할 |
| --- | --- |
| 오케스트레이터(FastAPI/RQ/Postgres) | API 호출·작업상태·슬랙 — **CPU·RAM 거의 안 먹음** |
| 영상 생성 | fal.ai 클라우드(Kling I2V) — 맥 자원 소모 X |
| 편집/검수 | 슬랙 + 필요 시 CapCut |

### 🎯 결론
- 개발·테스트는 맥북으로 충분
- ⚠️ **오케스트레이터는 상시 가동이 유리.** 맥이 슬립이면 fal.ai 작업 완료 후 파이프라인이 멈춤 → 초기엔 `caffeinate`로 버티되, **저렴한 상시 VPS(Oracle ARM 무료티어 등)로 오케스트레이터만 일찍 올리는 걸 권장.**

---

## 2. 제작 파이프라인 (I2V 코어)

### 2.1 핵심 흐름 (전부 API로 자동 호출)
```
① GPT        대본 + 비트별 감정·대사·emphasis (OpenAI API)
② fal.ai I2V 팡이 레퍼런스 이미지 → Kling I2V 클립 (fal-client SDK)
③ TTS        대사 줄별 음성 (Edge-TTS, 감정별 rate/pitch)
④ FFmpeg     클립·음성·자막(강조 포함)·BGM·SFX 합성
```

### 2.2 역할 분담
- **GPT = 글·지시** / **fal.ai(Kling) = 움직임(I2V)** / **TTS = 음성** / **FFmpeg = 조립**

### 2.3 ⭐ 일관성 — 생사 포인트
- 모든 비트 생성 시 **확정된 "팡이 마스터 레퍼런스"를 반드시 주입** (`PANGI_BODY`)
- 14감정은 표정·안테나 색만 프롬프트로 지정, *얼굴 구조·비율은 레퍼런스로 고정*
- 프롬프트: "Keep the exact same character design as the reference — do NOT redesign"

### 2.4 이미지를 어디서
- **Phase 1 (수동)**: Kling 플랫폼 UI에서 직접 → Elements/Subject로 일관성 확보 → 최적 프롬프트 발견
- **Phase 2+ (자동)**: fal.ai API (`fal-ai/kling-video/v1.6/standard/image-to-video`)
- Phase 1에서 확정한 프롬프트 템플릿을 코드에 박아 자동화

### 2.5 fal.ai API 운영
- **인증**: `FAL_KEY` 환경변수 하나 — SDK가 자동 처리
- **비동기**: `fal_client.submit(...).get()` — 폴링 코드 불필요
- **이미지 업로드**: `fal_client.upload_file(path)` → URL 반환 → I2V 입력
- 모델: `fal-ai/kling-video/v1.6/standard/image-to-video`

### 2.6 ⭐ 조립·편집 자동화 규칙 (구현 완료)

**(1) 호흡 / 컷 길이** — Phase 1 수동 1편에서 구체값 확정 후 코드 고정 예정
- 후킹: 첫 1초 안에 임팩트 / 꿀팁 컷: 말 끝나면 0.3~0.5초 트림
- 비트 전환은 하드컷 / 전체 30초 타이트 유지

**(2) 효과음(SFX) 맵 — ✅ 구현 완료**
- 비트 타입별 자동 삽입: 후킹→hook.wav / 본심수신→signal.wav / 꿀팁3단→tip.wav / 마무리→punch.wav
- 감정 오버라이드: 멍함·재부팅→glitch.wav (허당 개그)
- `assets/sfx/`에 파일 넣으면 자동 적용 (없으면 스킵)

**(3) 자막 스타일 — ✅ 구현 완료**
- 카테고리별 색: 직장=네이비, 욕망=퍼플, 부부=코랄, 일상=민트
- **핵심 단어 강조**: GPT 대본의 `emphasis` 필드 → 72pt 강조색으로 자막 위 표시
- 하단 중앙, 본 자막 44pt + 강조 단어 72pt

**(4) BGM**
- 카테고리별 `bgm` 경로 자동 적용, 볼륨 덕킹 (음성 대비 12%)

**(5) 후킹·루프** — Phase 1 후 코드화 예정

---

## 3. ⭐ 감독형 자동화 아키텍처 (v4 핵심)

### 3.1 개념
파이프라인이 단계마다 **자동 생성**하고, 사람의 판단이 필요한 지점에서만 **슬랙으로 결과를 던져** 승인/재생성/수정을 받는다.

### 3.2 인프라 — ✅ 구현 완료
- **FastAPI** — `/jobs` 작업 수신 + `/slack/actions` 슬랙 액션 수신
- **RQ(Redis)** — `render_queue` / `upload_queue` 분리
- **PostgreSQL** — jobs / episodes / topics / votes / submissions
- **Slack Interactive** — `[승인] [재생성] [수정하기]` + 반려 사유 모달 + HMAC 검증

### 3.3 단계별 슬랙 게이트 — ✅ 1·4단계 구현, 2·3단계 미구현
> **싼 단계 게이트를 먼저, 비싼 I2V는 사람이 고른 것만.**

1. ✅ **대본(GPT, 자동)** → 슬랙 "대본 확인" → `[대본 승인]` / `[대본 재생성]`
2. ❌ **이미지 후보(컷당 2~3장)** → 슬랙에 후보 나열 → 베스트 선택 *(미구현 — 컷별 이미지 생성기 선행 필요)*
3. ❌ **선택 이미지만 I2V** → 슬랙 클립 미리보기 → 승인/반려 *(미구현)*
4. ✅ **조립 완료 최종 프리뷰** → `[승인(업로드)]` / `[반려]` / `[재생성]`

### 3.4 수정 루프 — 미구현 (Phase 3)
- 대본 레벨 / 컷 레벨 / 움직임 레벨별 타깃 재생성
- 승인된 컷 잠금

### 3.5 비용 가드 — ✅ 구현 완료
- **에피소드당 재생성 상한**: `MAX_REGEN_PER_EPISODE=5` (Redis 카운터)
- 상한 도달 시 슬랙 경고 + 재생성 차단
- 일일 비용 임계치 초과 시 큐 일시정지 (`DAILY_COST_LIMIT=1.0`)
- I2V 비용 자동 기록 (`daily_cost.py`)

---

## 4. 로드맵

### Phase 0 — 페르소나·레퍼런스·계정
- [x] `pangi_persona.yaml` 확정 (젤리 약점·14감정·4비트·홈감정)
- [ ] **팡이 마스터 레퍼런스 이미지 확정** (`assets/pang/base/body_front.png`) ← 최우선
- [x] OpenAI API 키
- [ ] **fal.ai 가입 + `FAL_KEY` 발급**
- [x] Slack 앱 + 토큰
- [ ] YouTube OAuth Refresh Token (`python scripts/get_youtube_token.py`)
- [x] `.env` 구조 확정

### Phase 1 — 수동 1편 끝까지 ★핵심 의식
- [ ] Kling 플랫폼 UI에서 팡이 레퍼런스로 비트별 클립 직접 생성 → 프롬프트 최적화
- [ ] TTS 보이스 생성 (`python scripts/generate_voice.py`)
- [ ] FFmpeg 조립 (`python scripts/render_short.py`)
- [ ] **완성·업로드**로 톤·일관성·완주율 검증
- [ ] **반복 가능한 프롬프트 템플릿 추출** → 코드에 고정 (파이프라인 입력값)
- [ ] §2.6(1)(5) 컷 길이·후킹 오버레이 구체값 확정 → 코드화

### Phase 2 — 비동기 파이프라인
- [x] FastAPI `/jobs` + RQ 큐
- [x] fal.ai API 연동 (`fal-client` SDK)
- [x] PostgreSQL 스키마 (jobs / episodes / topics / votes / submissions)
- [x] 재시도 지수 백오프 + 멱등키
- [ ] Docker Compose 올리기 + 실 구동 테스트

### Phase 3 — 슬랙 게이트 고도화
- [x] 대본 게이트 + 최종 영상 게이트
- [ ] 이미지 후보 게이트 (§3.3 step 2·3)
- [ ] 수정 루프 + 승인 컷 잠금 (§3.4)
- [ ] ngrok / Cloudflare Tunnel 세팅

### Phase 4 — 소재 엔진 + 업로드 자동
- [x] 4단 소재 엔진 코드 (`topic_engine.py`)
- [x] YouTube 자동 업로드 (`api/youtube.py`)
- [ ] YouTube OAuth Refresh Token 발급 + 실 업로드 테스트
- [ ] 댓글 투표 수집·집계 실 연동

### Phase 5 — 확장 (지속)
- [ ] SFX 라이브러리 파일 실제 제작/수집 (`assets/sfx/*.wav`)
- [ ] BGM 파일 제작/수집 (`assets/bgm/*.mp3`)
- [ ] 굿즈 IP (팡이 이모티콘→실물)
- [ ] 다채널 시 오케스트레이터 VPS 상시 가동

---

## 5. 소재 엔진 (떨어지지 않는 4단 우물)
1. **시청자 제보** (장기 메인): `POST /submissions`, 동의·익명화
2. **트렌드 마이닝**: 유형만 추출 + 데이터랩 검증
3. **아키타입 뱅크**: `prompts/archetype_bank.yaml` — 카테고리별 상황×해법
4. **AI 오리지널**: GPT가 위 입력 기반으로 새 사연 생성

---

## 6. 현재 .env 필수 항목

```bash
# 필수 (없으면 핵심 기능 차단)
OPENAI_API_KEY=...
FAL_KEY=...                          # fal.ai — I2V 생성
POSTGRES_PASSWORD=원하는비번
DATABASE_URL=postgresql://ai_theater:원하는비번@postgres:5432/ai_theater_db

# Slack (감독형 자동화)
SLACK_BOT_TOKEN=...
SLACK_SIGNING_SECRET=...
SLACK_CHANNEL=#ai-theater-alerts

# YouTube (업로드 단계)
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...            # python scripts/get_youtube_token.py 로 발급

# 비용 가드 (선택 — 기본값 있음)
DAILY_COST_LIMIT=1.0                 # 일일 OpenAI 상한 ($)
MAX_REGEN_PER_EPISODE=5              # 에피소드당 재생성 상한
```

---

## 7. 비용 가드레일

| 항목 | 단가 | 월 7~8편 (재생성 없음) |
| --- | --- | --- |
| GPT 대본 | $0.003/편 | ~$0.02 |
| 배경 이미지 | $0.053/장 | ~$0.4 |
| **fal.ai Kling I2V** | **$0.28/클립** | **~$11** (5클립×8편) |
| TTS (Edge-TTS) | 무료 | $0 |
| **합계** | | **~$12 (약 17,000원)** |

> **핵심:** I2V가 비용의 90%. fal.ai 종량제라 구독 불필요. 재생성 상한(5회)으로 폭주 방지.
> ⚠️ fal.ai 단가는 변동 가능 — 사용 전 대시보드에서 확인.

---

## 📌 지금 당장 해야 할 것

1. **팡이 마스터 레퍼런스 이미지 확정** — Kling UI에서 생성, `assets/pang/base/body_front.png`로 저장
2. **fal.ai 가입 + `FAL_KEY` 발급** → `.env`에 추가
3. **DB 비밀번호 설정** → `.env` `POSTGRES_PASSWORD` / `DATABASE_URL`
4. **Ep.01 수동 1편** — Kling UI로 직접 클립 생성, 프롬프트 최적화
5. **YouTube Refresh Token** — `python scripts/get_youtube_token.py`
