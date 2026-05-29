# 📡 본심 대변인 「팡이」 통합 실행 계획서 (v2)

> 채널 컨셉 전환 반영판 — AI 극장(동화·역사 IF) → 본심 대변인(1인 캐릭터·능청 공감 숏폼)
> MacBook Air M3 · 16GB · 10-core GPU · 170GB 가용 디스크 기준
> 작성일: 2026-05-29 (v1 → v2 개정)

---

## 0. 컨셉 요약 (왜 계획이 바뀌었나)

| 구분 | v1 (구버전) | v2 (현재) |
| --- | --- | --- |
| 채널 정체성 | AI 극장 — 동화·역사 IF 분기극 | 본심 대변인 — 팡이의 능청 공감 숏폼 |
| 캐릭터 | 다수 등장인물 연기 | **와이파이 캐릭터 1인(팡이) 고정** |
| 핵심 캐릭터 컨셉 | 와이파이 의인화 마스코트 | **남들 못 듣는 "본심 주파수"를 수신해 대신 까발려주는 능청 공범** |
| 콘텐츠 | 흥부전·신데렐라·역사 IF | 직장·욕망·부부·일상의 "은밀한 본심·잔머리" 꿀팁 |
| 영상 길이 | 60~90초 | **약 30초 숏폼** |
| 비주얼 제작 | **매 장면 AI 이미지 생성** (6장/편) | **2.5D 퍼펫 고정 에셋 조립** (1회 제작 후 재사용) |
| 소재 공급 | 시나리오 분기 투표 | **시청자 제보 + 트렌드 마이닝 + 아키타입 뱅크 + AI 오리지널** |
| 차별화 | 인터랙티브 동화 | 김햄찌가 "체념"이라면, 팡이는 **방법까지 코칭하는 "공범"** |

> **불변 철학:** Mac은 두뇌, 추후 클라우드는 공장. 코드는 처음부터 클라우드 이식 가능하게(Docker). 자동화 이전에 **수동 1편으로 품질부터 확정.**

---

## 1. 하드웨어 진단 — 무엇이 되고, 무엇이 안 되는가

| 항목 | 사양 | 프로젝트 영향 |
| --- | --- | --- |
| CPU | Apple M3 (4P+4E, 8코어) | FFmpeg 동시 렌더링 **최대 2 워커** 권장 |
| GPU | 10-core, Metal 3 | **VideoToolbox 하드웨어 인코딩** 활용 시 CPU 부담 1/3 |
| RAM | 16GB 통합 메모리 | Docker 한도 **8–10GB**, 나머지는 시스템/브라우저 |
| 저장공간 | 170GB 여유 | 퍼펫 에셋 라이브러리 고정(~수 GB) + 편당 임시파일 ≈ 150MB(정적 합성이라 v1보다 가벼움) |
| 발열 | **팬리스 (MacBook Air)** | 30분 이상 풀로드 시 스로틀링 → 24/7 운영 부적합 |
| 네트워크 | 노트북 (Wi-Fi/슬립) | YouTube 업로드 중 슬립 위험 → **caffeinate** 필수 |

### 🎯 결론
- **개발·MVP·소량 운영(하루 1~3편 숏폼)** → 이 맥북으로 충분
- 2.5D 퍼펫 조립 방식은 매 장면 이미지 생성보다 **연산이 가벼워** Air에 유리
- **24/7·다채널 단계** → 클라우드(Hetzner / Oracle ARM 무료티어)로 이전 (Docker 그대로 이식)

---

## 2. 로컬 개발 환경 + 제작 파이프라인 (Apple Silicon 최적화)

### 2.1 베이스 도구
```
- Homebrew (ARM64)
- Python 3.11 (pyenv 관리 — 3.10+ 충족)
- OrbStack (Docker Desktop 대안, 메모리 ~30% 절약) ← 16GB RAM에서 강력 추천
  · Resources: CPU 4, RAM 8GB, Swap 2GB, Disk 60GB
- ffmpeg (brew install ffmpeg — VideoToolbox 자동 포함)
- redis, postgresql@16 (개발은 brew 로컬, 배포는 Docker)
```

### 2.2 ⭐ 캐릭터 에셋 모델 — 가장 크게 바뀐 부분

**v1의 "매 장면 AI 이미지 생성"은 폐기.** 캐릭터 일관성이 매번 깨지는 문제 때문. 대신 **팡이를 한 번 만들고 계속 재사용하는 퍼펫 방식**으로 전환한다.

**(1) 퍼펫 에셋 1회 제작**
- 확정된 팡이 2.5D 렌더를 **레이어별로 분리**: 몸통 / 머리 / 안테나(L·R) / 눈(L·R) / 입 / 팔
- **14감정 파츠 라이브러리**: 눈 아이콘 14종 + 안테나 색·형태 14종을 교체 가능한 부품으로 보관
  - `assets/pang/base/`, `assets/pang/eyes/<emotion>.png`, `assets/pang/antenna/<emotion>.png`

**(2) 모션 클립 라이브러리 사전 렌더 (핵심 자동화 전제)**
- 리깅 툴(Live2D Cubism 또는 After Effects)로 **재사용 가능한 짧은 루프 클립**을 미리 렌더해 둔다:
  - `idle`(대기), `talk`(말하기 루프), 그리고 14감정별 리액션 1~2초 클립
  - `assets/pang/clips/<state>.mov` (알파 채널 포함)
- 이후 자동 파이프라인은 **이 클립들을 감정 비트 순서대로 이어 붙이기만** 하면 됨 → 일관성 100%, 연산 가벼움

**(3) 배경·소품은 AI 생성 허용**
- 배경은 캐릭터 일관성 문제가 없으므로 정적 AI 이미지 생성 OK (`assets/bg/<topic>.webp`)
- 즉 "캐릭터=퍼펫 고정, 배경=AI 생성"의 하이브리드

### 2.3 FFmpeg 가속 — M3 GPU 활용 + 퍼펫 합성
```bash
# 하드웨어 가속 인코딩 (M3 GPU) — 렌더링 3~5배 ↑
ffmpeg -i scene.mov -c:v h264_videotoolbox -b:v 4M out.mp4

# 퍼펫 클립 + 배경 + TTS + 자막 합성 (개념)
ffmpeg -i bg.webp -i pang_talk.mov -i voice.mp3 \
  -filter_complex "[0][1]overlay=...[v];[v]drawtext=...[vt]" \
  -map "[vt]" -map 2:a -c:v h264_videotoolbox out.mp4
```
→ 30초 1편: CPU 인코딩 ~50초 vs VideoToolbox ~12초

### 2.4 Docker Compose 리소스 가드레일
```yaml
api:        memory: 512M   cpus: '0.5'
worker:     memory: 3G     cpus: '2.0'   # FFmpeg 합성이 가장 무거움
redis:      memory: 256M
postgres:   memory: 1G
```

---

## 3. 단계별 로드맵

### Phase 0 — 사전 준비 + 캐릭터 에셋 (1.5주)
- [ ] Mac 개발 환경 구축 (Homebrew, Python, OrbStack)
- [x] Git 구조 확정: `/api`, `/worker`, `/scripts`, `/prompts`, `/assets`, `/docker`
- [ ] OpenAI / Slack / YouTube API 키 발급 + 권한 최소화
- [x] **팡이 페르소나·보이스 가이드 확정** → `prompts/pangi_persona.yaml`
- [ ] **팡이 퍼펫 에셋 제작**: 레이어 분리 + 14감정 파츠 + idle/talk/감정 클립 라이브러리
- [x] `.env.example` v2 기준 재작성 + 퍼펫 에셋 경로 변수 추가

### Phase 1 — "수동으로" 1편 만들기 (2주)
> 자동화 이전에 **결과물 품질·톤부터 확정**
- [x] GPT로 **팡이 Ep.01 스크립트** 생성 → `generate_script.py` (후킹→본심수신→꿀팁3단→마무리 포맷 확정)
- [x] Edge-TTS 보이스 생성 → `generate_voice.py` (팡이 단일 화자, 14감정 모듈레이션)
- [x] **퍼펫 클립 조립** → `render_short.py` (퍼펫 오버레이 + 폴백 정적 렌더 지원)
- [x] 배경 이미지 생성 → `generate_image.py` (배경 전용, 카테고리별 스타일)
- [x] `manual_run.py` v2 파이프라인 연결 (대본→배경→보이스→렌더 순서)
- [ ] 퍼펫 에셋 제작 완료 후 **수동 1편 실제 렌더링** → 업로드해 톤·길이·자막·후킹 검증

### Phase 2 — 비동기 워커 & 상태 관리 (2주)
- [x] FastAPI `/jobs` POST → Job ID 즉시 반환, category/episode_no 파라미터
- [x] RQ 워커: `render_queue` / `upload_queue` 분리 유지
- [x] PostgreSQL 스키마 v2: `jobs`, `episodes`(category), `topics`, `votes`, `submissions` → `db/models.py`, `docker/init.sql`
- [x] 재시도 정책: 지수 백오프(1m→5m→30m), 3회 실패 시 `send_error_alert` Slack 알람
- [x] **멱등키:** `job_id`를 YouTube 설명에 `ref:{job_id}` 형식으로 포함

### Phase 3 — Slack Human-in-the-loop (1.5주)
- [ ] Slack App + Interactive Components URL = `https://<ngrok>/slack/actions` (사용자 직접 설정)
- [x] `X-Slack-Signature` HMAC 검증 → `api/slack.py` `verify_slack_signature`
- [x] 워커 렌더 완료 → Slack에 프리뷰 mp4 + `[승인]/[반려]/[재생성]` 버튼 → `worker/slack_notifier.py`
- [x] 승인 → `upload_queue` / 반려 → 사유 modal(`reject_reason_modal`) → DB 기록 / 재생성 → `render_queue` 재투입
- [ ] 로컬 개발 중 ngrok / Cloudflare Tunnel 실행 (사용 후 수동 종료)

### Phase 4 — YouTube 자동 업로드 (1주)
- [ ] OAuth 2.0 refresh token 저장 (Postgres 암호화 필드)
- [ ] **Resumable Upload** 필수 (Wi-Fi 끊겨도 이어서 업로드)
- [ ] 업로드 중 `caffeinate -dims`로 슬립 차단
- [ ] 메타데이터 자동 생성: 타이틀 공식(`[도발적 본심 질문] + [주제] | 팡이 Ep.XX`), 태그, 썸네일

### Phase 5 — 소재 엔진 + 인터랙티브 루프 ⭐ 차별화 (2.5주)
> v1의 "댓글 투표 수집"만으론 부족 → **4단 소스 엔진**으로 확장
- [ ] **(1) 시청자 제보**: 영상 CTA + 구글폼/댓글 수집 → `submissions` 적재 (동의·익명화 처리)
- [ ] **(2) 트렌드 마이닝**: 커뮤니티 인기글·유사채널 댓글에서 "반복되는 본심/빡침 *유형*"만 추출(원문 X) + 네이버 데이터랩/구글 트렌드 API로 상승세 검증
- [ ] **(3) 아키타입 뱅크**: "본심 상황 유형 × 능청 해법" 조합 라이브러리 → 입력 0에서도 무한 생성
- [ ] **(4) AI 오리지널**: 위 입력값으로 GPT가 *완전 새 사연* 생성 (저작권·양산정책 안전)
- [ ] `comments_collector`: 발행 48시간 후 댓글 수집 → "다음 본심 주제" 키워드 매칭(정규식+LLM 보조)
- [ ] `votes` 누적 → 최다 표 → 다음 화 주제 시드로 GPT 호출
- [ ] Slack 일일 리포트: "Ep.03 다음 본심 투표: 월요병 탈출 312표 vs 칼퇴 명분 87표 → 차주 주제 확정"

### Phase 6 — 콘텐츠·IP 확장 (지속)
**본심 카테고리** 단위로 템플릿화 (v1의 동화→역사IF 경로 폐기)
- [ ] 카테고리별 프롬프트 모듈화: `/prompts/work.yaml`(직장), `/prompts/desire.yaml`(욕망), `/prompts/couple.yaml`(부부), `/prompts/daily.yaml`(일상)
- [ ] 카테고리별 자막 스타일·BGM·인트로 차별화
- [ ] **굿즈 IP 확장**: 팡이 이모티콘 → 실물 굿즈 (자체 IP라 저작권 충돌 0)

---

## 4. 비용 가드레일

| 항목 | 일일 상한 | 월 예상 (숏폼 30편 기준) |
| --- | --- | --- |
| OpenAI (스크립트 GPT-4o-mini) | $1 | ~$15 |
| OpenAI (배경 이미지, 편당 1~2장) | $0.3 | ~$3 (캐릭터는 퍼펫 재사용이라 0) |
| Edge-TTS | 무료 | $0 |
| YouTube API | 쿼터 10,000 unit/day | $0 |
| **합계** | — | **~$18** (v1 대비 ↓, 이미지 생성량 급감) |

> **퍼펫 전환 효과:** 편당 6장 이미지 생성이 사라져 이미지 비용이 거의 0에 수렴. 대신 **퍼펫 에셋 제작은 1회성 초기 비용**(외주 또는 직접 제작 시간).

### AI 영상(Kling 등) 전환 — 보류
- 2.5D 퍼펫을 직접 애니메이션하므로 **캐릭터용 AI 영상은 불필요.**
- Kling 등은 필요 시 **배경 B-roll 용도로만** 선택 검토.

### 자동 차단 로직
- `daily_cost.py`가 매일 자정 OpenAI usage API 호출 → 임계치 초과 시 `jobs` 큐 일시 정지

---

## 5. 디스크/메모리 관리 정책 (170GB 환경)

- **퍼펫 에셋 라이브러리**(`assets/pang/`)는 영구 보관 — 수 GB, 버전 관리
- 편당 임시 파일은 `/tmp/aitheater/<job_id>/` → 완료/실패 후 **24시간 내 자동 삭제**(cron)
- 최종 mp4는 YouTube 업로드 성공 시 즉시 삭제, Postgres엔 YouTube ID만
- 배경 캐시 풀 상한: **10GB**(LRU) — 정적 배경이라 v1보다 작게
- `docker system prune -af --volumes` 주 1회 cron

---

## 6. 보안 체크리스트

- [ ] `.env`는 `.gitignore` 최상단, pre-commit에 `gitleaks` 훅
- [ ] Slack Signing Secret 검증 **모든 엔드포인트에서**
- [ ] YouTube OAuth scope: `youtube.upload` + `youtube.force-ssl`(댓글 읽기) **만**
- [ ] Postgres 비밀번호는 Docker secrets, 환경변수 평문 노출 X
- [ ] 시청자 제보(`submissions`)는 **동의·익명화** 처리, 개인 식별정보 제거
- [ ] 로컬 ngrok 터널은 **수동 종료 습관화**

---

## 7. 클라우드 이전 트리거

다음 중 **2개 이상** 시 VPS 이전:
- 일 자동 발행 ≥ 3편
- 동시 채널 ≥ 2개
- 렌더링 중 MacBook 발열로 작업 지장
- 노트북 외출 잦아 24/7 운영 불가

**추천 타깃:** Hetzner CPX31 (4 vCPU / 8GB / €13/mo) 또는 Oracle Cloud ARM Ampere A1 (4 vCPU / 24GB 무료) — Docker Compose 그대로 이식

---

## 📌 즉시 다음 액션 (이번 주)
1. **팡이 페르소나·보이스 가이드 확정** (이름·말투·캐치프레이즈)
2. **퍼펫 에셋 제작** — 레이어 분리 + 14감정 파츠 + idle/talk/감정 클립 라이브러리
3. OrbStack 설치 + 디렉토리 스캐폴딩(`api/`, `worker/`, `assets/`, `docker-compose.yml`)
4. OpenAI 키 발급 + `.env.example` 작성
5. **팡이 Ep.01 수동 1편 만들기** ("상사 몰래 쉬는 법") — Phase 1의 핵심 의식
