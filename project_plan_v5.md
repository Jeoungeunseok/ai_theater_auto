# 📡 본심 대변인 「팡이」 통합 실행 계획서 (v5)

> 파이프라인 순서 정정판 — v4 + **TTS-FIRST 순서 교정 / 이미지 생성 단계 명시 / 무음 I2V 명시**
> 벤치마크: 정서불안 김햄찌 (이미지 생성 + I2V 방식)
> MacBook Air M3 · 16GB · 작성일: 2026-05-30 / v5 수정: 2026-06-01

---

## ✏️ v4 → v5 핵심 변경점 (먼저 읽기)

1. **(제일 중요) 파이프라인 순서: I2V-first → TTS-FIRST 로 교정.** v4 §2.1은 I2V를 먼저 생성한 뒤 TTS를 붙이는 순서였는데, TTS 길이를 *먼저* 알아야 컷 길이(5s/10s)와 자막 타이밍을 맞출 수 있음. ⚠️ 이미 코드가 I2V-first로 짜여 있다면 렌더 파이프라인 순서를 바꿔야 함.
2. **이미지 생성 단계를 명시.** v4는 "팡이 레퍼런스 이미지 → I2V"로 *그 이미지를 어떻게 만드는지*가 빠져 있었음. 컷별로 (레퍼런스+감정+장면)으로 정지 이미지를 먼저 생성하는 단계를 추가 — 이게 §3.3의 "싼 이미지 게이트" 자리이기도 함.
3. **무음 I2V 명시.** I2V 호출에 `generate_audio=false`(무음)로 박음. 음성은 TTS가 담당(네이티브 오디오 비용 ~2배, 한국어 불안정, 목소리 흔들림 회피).
4. **모델 버전 결정 플래그.** v4는 `kling-video/v1.6/standard`를 지정했는데, 일관성 핵심 기능(`elements`)은 상위 모델(v3 / 2.6 Pro)에 있음 — 일관성 vs 단가 트레이드오프 확인 필요(§2.4).
5. **선택적 LipSync** 항목 추가(정면 말하는 컷만, 고급 단계).

---

## 0. 무엇이 바뀌었나 (v3 → v4 → v5)

| 구분 | v3 | v4 | v5 |
| --- | --- | --- | --- |
| 자동화 | 수동 중심 | 감독형 자동화 | (유지) |
| 영상 생성 API | Kling 직접 | **fal.ai 종량제** | (유지) |
| **파이프라인 순서** | — | I2V → TTS | **TTS → 이미지 → 무음 I2V → 합성** |
| 이미지 생성 | 암묵적 | 암묵적 | **명시 단계 + 싼 게이트** |
| 오디오 | — | (불명확) | **TTS 전담 / I2V는 generate_audio=false** |

> **불변 철학:** 자동화 이전에 **수동 1편으로 품질부터 확정.** 사람은 "선별자·승인자"이지 "무한 생성기"가 아니다.

---

## 1. 하드웨어 — 가벼운 오케스트레이터 + 클라우드 생성

무거운 영상 생성은 **fal.ai 클라우드(Kling I2V)**가 대행. 로컬엔 *가벼운 오케스트레이터*(API 호출·작업상태·슬랙)만 남는다.

| 항목 | 역할 |
| --- | --- |
| 오케스트레이터(FastAPI/RQ/Postgres) | API 호출·작업상태·슬랙 — CPU·RAM 거의 안 먹음 |
| 영상 생성 | fal.ai 클라우드(Kling I2V) — 맥 자원 소모 X |
| 편집/검수 | 슬랙 + 필요 시 CapCut |

### 🎯 결론
- 개발·테스트는 맥북으로 충분
- ⚠️ **오케스트레이터는 상시 가동이 유리.** 맥이 슬립이면 fal.ai 작업 완료 후 파이프라인이 멈춤 → 초기엔 `caffeinate`, 이후 저렴한 상시 VPS(Oracle ARM 무료티어 등)로 오케스트레이터만 일찍 이전 권장.

---

## 2. 제작 파이프라인 (I2V 코어)

### 2.1 핵심 흐름 — ⚠️ TTS-FIRST (v5 정정)
```
① GPT        대본 + 비트별 감정·대사·emphasis (OpenAI API)
② TTS        대사 줄별 음성 생성 (Edge-TTS) → 파일 길이 측정      ← 먼저!
③ 길이 결정   TTS 길이로 Kling 생성 길이(5s/10s) 결정
④ 이미지      팡이 레퍼런스 + 감정 + 장면 → 컷별 정지 이미지 생성   ← 명시 추가
⑤ fal.ai I2V  ④ 이미지 → Kling I2V (generate_audio=false, 무음 영상)
⑥ FFmpeg     영상을 TTS 길이로 트림 + 음성·자막(강조)·SFX·BGM 합성
(선택)        정면으로 말하는 컷만 LipSync 적용
```

**왜 TTS 먼저?** ① 컷 길이를 음성 기준으로 정함 ② 자막 싱크를 음성 파일 길이로 잡음 ③ 팡이 목소리를 TTS로 고정(네이티브 오디오는 컷마다 톤이 흔들림).

**길이 결정 규칙:**
```
TTS ≤ 4.5s  → Kling 5s 생성  → (TTS + 0.4s)로 트림
TTS 4.5~9.5s → Kling 10s 생성 → (TTS + 0.4s)로 트림
```
> ⚠️ **5초 최소 과금**: Kling은 5s 단위라 2.6s 대사 컷도 5s치 비용. 짧은 컷을 잔뜩 만들면 낭비 → 대사를 5s에 가깝게 채우거나 짧은 컷은 합치는 게 유리.

### 2.2 역할 분담
- **GPT = 글·지시** / **fal.ai(Kling) = 움직임(I2V, 무음)** / **TTS = 음성** / **FFmpeg = 조립**

### 2.3 ⭐ 일관성 — 생사 포인트
- 모든 컷 이미지 생성 시 **확정된 "팡이 마스터 레퍼런스"를 반드시 주입** (`PANGI_BODY`)
- 14감정은 표정·안테나 색만 프롬프트로 지정, *얼굴 구조·비율은 레퍼런스로 고정*
- 프롬프트: "Keep the exact same character design as the reference — do NOT redesign"

### 2.4 이미지 생성 — 어디서 / 어떤 모델
- **Phase 1 (수동)**: Kling 플랫폼 UI에서 직접 → Elements/Subject로 일관성 확보 → 최적 프롬프트 발견
- **Phase 2+ (자동)**: fal.ai API로 컷별 이미지 생성(레퍼런스 + 감정 + 장면) → 그 이미지를 I2V 입력으로
- ⚠️ **모델 버전 결정**: v4가 지정한 `kling-video/v1.6/standard`는 구형·저비용이나 캐릭터 일관성 기능(`elements`/multi-ref)이 약함. 일관성이 생사인 프로젝트라, **`elements` 지원 상위 모델(예: Kling v3 / 2.6 Pro 계열)**을 일관성-단가 비교 후 선택 권장. Phase 1 테스트로 결정.

### 2.5 fal.ai API 운영
- **인증**: `FAL_KEY` 환경변수 하나 — SDK 자동 처리
- **비동기**: `fal_client.submit(...).get()` — 폴링 코드 불필요
- **이미지 업로드**: `fal_client.upload_file(path)` → URL → 이미지/I2V 입력
- **무음**: I2V 호출에 `generate_audio=false` (음성은 TTS 전담)
- **결과 즉시 저장**: 생성 결과 링크는 만료(약 24h)될 수 있으니 완료 즉시 파일 다운로드·보관

### 2.6 ⭐ 조립·편집 자동화 규칙

**(1) 호흡 / 컷 길이** — Phase 1 수동 1편에서 구체값 확정 후 코드 고정 예정
- 후킹: 첫 1초 안에 임팩트 / 꿀팁 컷: 말 끝나면 0.3~0.5초 트림 / 비트 전환 하드컷 / 전체 30초 타이트

**(2) 효과음(SFX) 맵 — ✅ 구현 완료**
- 비트 타입별 자동: 후킹→hook.wav / 본심수신→signal.wav / 꿀팁3단→tip.wav / 마무리→punch.wav
- 감정 오버라이드: 멍함·재부팅→glitch.wav (젤리 허당 개그)
- `assets/sfx/`에 파일 넣으면 자동 적용 (없으면 스킵)

**(3) 자막 스타일 — ✅ 구현 완료**
- 카테고리별 색: 직장=네이비 / 욕망=퍼플 / 부부=코랄 / 일상=민트
- 핵심 단어 강조: GPT 대본 `emphasis` 필드 → 72pt 강조색. 본 자막 44pt, 하단 중앙
- 자막 타이밍은 ②에서 측정한 TTS 길이 기준(SRT/ASS)

**(4) BGM** — 카테고리별 `bgm` 자동 적용, 볼륨 덕킹(음성 대비 12%)

**(5) 후킹·루프** — Phase 1 후 코드화 예정

**(6) 선택적 LipSync (고급)** — 정면에서 직접 말하는 컷만 fal Kling LipSync(video_url+audio_url)로 입 맞춤. ⚠️ 트림 *후* TTS와 싱크. 전 컷 적용 금지(비용·불필요).

---

## 3. ⭐ 감독형 자동화 아키텍처

### 3.1 개념
파이프라인이 단계마다 **자동 생성**하고, 판단이 필요한 지점에서만 **슬랙으로 결과를 던져** 승인/재생성/수정.

### 3.2 인프라 — ✅ 구현 완료
- **FastAPI** — `/jobs` + `/slack/actions`
- **RQ(Redis)** — `render_queue` / `upload_queue`
- **PostgreSQL** — jobs / episodes / topics / votes / submissions
- **Slack Interactive** — `[승인] [재생성] [수정하기]` + 반려 모달 + HMAC 검증

### 3.3 단계별 슬랙 게이트 — ✅ 1·4단계 / ❌ 2·3단계
> **싼 단계 먼저, 비싼 I2V는 사람이 고른 것만.**
1. ✅ **대본(GPT)** → 슬랙 "대본 확인" → `[승인]`/`[재생성]`
2. ❌ **이미지 후보(컷당 2~3장)** → 슬랙 후보 나열 → 베스트 선택 *(미구현 — §2.1 ④ 컷별 이미지 생성기가 선행돼야 함. 가장 중요한 미구현 = 비용 게이트)*
3. ❌ **선택 이미지만 I2V** → 슬랙 클립 미리보기 → 승인/반려 *(미구현)*
4. ✅ **조립 완료 최종 프리뷰** → `[승인(업로드)]`/`[반려]`/`[재생성]`

### 3.4 수정 루프 — ❌ 미구현 (Phase 3)
- 대본 레벨 / 컷 레벨 / 움직임 레벨별 타깃 재생성 + 승인 컷 잠금

### 3.5 비용 가드 — ✅ 구현 완료
- 에피소드당 재생성 상한 `MAX_REGEN_PER_EPISODE=5` (Redis 카운터) → 도달 시 슬랙 경고 + 차단
- 일일 비용 임계치 초과 시 큐 일시정지 `DAILY_COST_LIMIT=1.0`
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
- [ ] Kling UI에서 팡이 레퍼런스로 비트별 클립 직접 생성 → 프롬프트·모델 최적화
- [ ] TTS 보이스 생성 + **길이 측정** (`python scripts/generate_voice.py`)
- [ ] FFmpeg 조립 (TTS 길이 기준 트림·자막, `python scripts/render_short.py`)
- [ ] **완성·업로드**로 톤·일관성·완주율 검증
- [ ] **반복 가능한 프롬프트 템플릿 추출** → 코드 고정
- [ ] §2.6(1)(5) 컷 길이·후킹 구체값 확정 → 코드화

### Phase 2 — 비동기 파이프라인
- [x] FastAPI `/jobs` + RQ 큐
- [x] fal.ai API 연동 (`fal-client` SDK)
- [x] PostgreSQL 스키마
- [x] 재시도 지수 백오프 + 멱등키
- [ ] **렌더 파이프라인 순서를 TTS-FIRST로 점검/수정** ← v5 신규 (코드가 I2V-first면 교정)
- [ ] Docker Compose 올리기 + 실 구동 테스트

### Phase 3 — 슬랙 게이트 고도화
- [x] 대본 게이트 + 최종 영상 게이트
- [ ] **컷별 이미지 생성기 구현** → 이미지 후보 게이트(§3.3 step 2·3) ← 최우선 미구현
- [ ] 수정 루프 + 승인 컷 잠금 (§3.4)
- [ ] ngrok / Cloudflare Tunnel 세팅

### Phase 4 — 소재 엔진 + 업로드 자동
- [x] 4단 소재 엔진 코드 (`topic_engine.py`)
- [x] YouTube 자동 업로드 (`api/youtube.py`)
- [ ] YouTube OAuth Refresh Token 발급 + 실 업로드 테스트
- [ ] 댓글 투표 수집·집계 실 연동

### Phase 5 — 확장 (지속)
- [ ] SFX 라이브러리 제작/수집 (`assets/sfx/*.wav`)
- [ ] BGM 제작/수집 (`assets/bgm/*.mp3`)
- [ ] (선택) 정면 말하는 컷 LipSync 연동
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
# 필수
OPENAI_API_KEY=...
FAL_KEY=...                          # fal.ai — 이미지·I2V 생성
POSTGRES_PASSWORD=원하는비번
DATABASE_URL=postgresql://ai_theater:원하는비번@postgres:5432/ai_theater_db

# Slack (감독형 자동화)
SLACK_BOT_TOKEN=...
SLACK_SIGNING_SECRET=...
SLACK_CHANNEL=#ai-theater-alerts

# YouTube (업로드 단계)
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...            # python scripts/get_youtube_token.py

# 비용 가드 (기본값 있음)
DAILY_COST_LIMIT=1.0
MAX_REGEN_PER_EPISODE=5
```

---

## 7. 비용 가드레일

| 항목 | 단가(대략) | 월 7~8편 (재생성 없음) |
| --- | --- | --- |
| GPT 대본 | $0.003/편 | ~$0.02 |
| 컷별 이미지 | 컷당 소액 | ~$0.4 |
| **fal.ai Kling I2V (무음)** | **약 $0.07/s (5s≈$0.35)** | **~$11~14** |
| TTS (Edge-TTS) | 무료 | $0 |
| **합계** | | **~$12~15 (약 17,000~21,000원)** |

> **핵심:** I2V가 비용의 ~90%. `generate_audio=false`로 네이티브 오디오(~2배) 회피. 5초 최소 과금 + 재생성 상한(5회)으로 폭주 방지. 모델 버전(v1.6 vs v3/2.6 Pro)에 따라 단가·일관성이 갈리니 Phase 1에서 확정.
> ⚠️ fal.ai 단가·모델 라인업은 변동 가능 — 사용 전 대시보드 확인.

---

## 📌 지금 당장 해야 할 것
1. **팡이 마스터 레퍼런스 이미지 확정** — Kling UI 생성, `assets/pang/base/body_front.png`
2. **fal.ai 가입 + `FAL_KEY` 발급** → `.env` 추가 + Phase 1에서 모델 버전 결정(일관성)
3. **DB 비밀번호 설정** → `.env`
4. **Ep.01 수동 1편** — Kling UI 직접 생성, 프롬프트 최적화 (+ TTS 길이→트림 흐름 손으로 검증)
5. **렌더 파이프라인 TTS-FIRST 점검** — 코드가 I2V-first면 순서 교정
6. **YouTube Refresh Token** — `python scripts/get_youtube_token.py`
