# 🎬 AI 극장(AI Theater) 통합 실행 계획서

> MacBook Air M3 · 16GB · 10-core GPU · 170GB 가용 디스크 기준
> 작성일: 2026-05-18

---

## 1. 하드웨어 진단 — 무엇이 되고, 무엇이 안 되는가

| 항목 | 사양 | 프로젝트 영향 |
| --- | --- | --- |
| CPU | Apple M3 (4P+4E, 8코어) | FFmpeg 동시 렌더링 **최대 2 워커** 권장 |
| GPU | 10-core, Metal 3 | **VideoToolbox 하드웨어 인코딩** 활용 시 CPU 부담 1/3 |
| RAM | 16GB 통합 메모리 | Docker 한도 **8–10GB**, 나머지는 시스템/브라우저 |
| 저장공간 | 170GB 여유 | 쇼츠 1편 임시파일 ≈ 300MB → **반드시 자동 정리 정책** |
| 발열 | **팬리스 (MacBook Air)** | 30분 이상 풀로드 시 스로틀링 → 24/7 운영 부적합 |
| 네트워크 | 노트북 (Wi-Fi/슬립) | YouTube 업로드 중 슬립 위험 → **caffeinate** 필수 |

### 🎯 결론
- **개발·MVP·소량 운영 (하루 1–3편 쇼츠 생성)** → 이 맥북으로 충분
- **24/7 자동화·다채널 확장 단계** → 클라우드(VPS, 예: Hetzner CPX31, Oracle ARM Ampere 무료티어)로 이전 권장
- **현 단계 전략:** "Mac은 두뇌, 추후 클라우드는 공장" — 코드는 처음부터 클라우드 이식 가능하게 짠다 (그래서 Docker가 중요)

---

## 2. 로컬 개발 환경 설정 (Apple Silicon 최적화)

### 2.1 베이스 도구
```
- Homebrew (ARM64)
- Python 3.11 (pyenv 관리 권장 — 3.10+ 요구사항 충족)
- Docker Desktop for Apple Silicon  → Resources: CPU 4, RAM 8GB, Swap 2GB, Disk 60GB
- OrbStack (Docker Desktop 대안, 메모리 절약 ~30%) ← 16GB RAM에서 강력 추천
- ffmpeg (brew install ffmpeg — VideoToolbox 자동 포함)
- redis, postgresql@16 (개발 중엔 brew 로컬 설치, 배포는 Docker)
```

### 2.2 FFmpeg 가속 — M3 GPU 활용
```bash
# CPU 인코딩 (느림, 호환성 ↑)
ffmpeg -i in.mp4 -c:v libx264 ...

# 하드웨어 가속 (M3 GPU) — 렌더링 속도 3~5배 ↑
ffmpeg -i in.mp4 -c:v h264_videotoolbox -b:v 4M ...
```
→ 쇼츠 60초 1편 기준: CPU 인코딩 ~90초 vs VideoToolbox ~20초

### 2.3 Docker Compose 리소스 가드레일
각 서비스에 `deploy.resources.limits` 명시 — 16GB 환경에서 가장 중요한 한 줄들:
```yaml
api:        memory: 512M   cpus: '0.5'
worker:     memory: 3G     cpus: '2.0'   # FFmpeg가 가장 무거움
redis:      memory: 256M
postgres:   memory: 1G
```

---

## 3. 단계별 로드맵 (현실적 일정 포함)

### Phase 0 — 사전 준비 (1주, 5/18 ~ 5/25)
- [ ] Mac 개발 환경 구축 (Homebrew, Python, Docker/OrbStack)
- [ ] `.env.example` 작성 + 1Password/`age` 기반 시크릿 관리 컨벤션 결정
- [ ] Git 저장소 구조 확정: `/api`, `/worker`, `/scripts`, `/prompts`, `/docker`
- [ ] OpenAI / Slack / YouTube API 키 발급 + 권한 최소화 (가이드 §2 준수)

### Phase 1 — 영상 1편을 "수동으로" 만들어보기 (2주)
> 자동화 이전에 **파이프라인이 만드는 결과물 품질부터 확정**
- [ ] OpenAI로 흥부전 1편 스크립트 생성 (프롬프트 v1 확정)
- [ ] Edge-TTS로 보이스 생성 (한국어 화자 후보 비교: ko-KR-SunHi/InJoon 등)
- [ ] 장면 이미지: **gpt-image-2** (세로형 1024×1536, medium 품질)
  - 시리즈 컨셉아트를 `storage/bg_pool/<series>_concept.webp`에 두면 레퍼런스 이미지로 자동 활용
  - 품질/비용 조절: `.env`에 `IMAGE_QUALITY=low|medium|high` 설정
- [ ] FFmpeg `drawtext`로 자막 합성 스크립트 (`render_short.py`) — **이게 코어**
- [ ] **수동 1편 완성** → 채널에 업로드해보고 톤·길이·자막 가독성 확정

### Phase 2 — 비동기 워커 & 상태 관리 (2주)
- [ ] FastAPI `/jobs` POST → Job ID 즉시 반환 (3-sec ACK)
- [ ] RQ 워커 분리, `render_queue` / `upload_queue` 두 개로 분할
- [ ] PostgreSQL 스키마:
  ```
  jobs(id, status, current_step, retry_count, error_log, created_at, ...)
  episodes(id, series, episode_no, script_id, video_path, youtube_id, ...)
  votes(episode_id, choice_key, count, snapshot_at)   -- Phase 5용 미리 설계
  ```
- [ ] 재시도 정책: 지수 백오프 (1m → 5m → 30m), 3회 실패 시 Slack 알람
- [ ] **멱등키:** `job_id`를 YouTube 업로드 메타에 박아 중복 업로드 차단

### Phase 3 — Slack Human-in-the-loop (1.5주)
- [ ] Slack App 생성 + Interactive Components URL = `https://<ngrok>/slack/actions`
- [ ] `X-Slack-Signature` HMAC 검증 미들웨어 (가이드 §2 — 위조 차단)
- [ ] 워커가 렌더 완료 → Slack에 프리뷰 mp4 + `[승인]/[반려]/[재생성]` 버튼
- [ ] 승인 시 → `upload_queue`로 전달, 반려 시 → 사유 modal → DB 기록
- [ ] **로컬 개발 중엔 ngrok / Cloudflare Tunnel** 사용 (Mac이 외부 노출 X)

### Phase 4 — YouTube 자동 업로드 (1주)
- [ ] OAuth 2.0 refresh token 저장 (Postgres `secrets` 테이블, 암호화 필드)
- [ ] **Resumable Upload** 필수 — Wi-Fi 끊겨도 이어서 업로드
- [ ] 업로드 중엔 `caffeinate -dims` 로 슬립 차단
- [ ] 메타데이터 자동 생성: 타이틀 공식(`[자극질문]+[주제]+Ep.XX`), 태그, 썸네일

### Phase 5 — 인터랙티브 피드백 루프 ⭐ 차별화 포인트 (2주)
- [ ] `comments_collector` 워커: YouTube Data API로 N+1편 발행 48시간 후 댓글 수집
- [ ] 선택지 키워드 매칭 (예: "치료" vs "외면") → 정규식 + LLM 보조 분류
- [ ] `votes` 테이블 누적 → 가장 많은 표 → 다음 화 시나리오 시드로 OpenAI 호출
- [ ] Slack 일일 리포트: "Ep.03 투표 결과: 치료 312표, 외면 87표 → 차주 시나리오 분기 확정"

### Phase 6 — 콘텐츠 IP 확장 (지속)
구전동화 → 역사IF → 추리 → 시뮬레이션 순으로 **시리즈 템플릿화**
- [ ] 시리즈별 프롬프트 모듈화 (`/prompts/folktale.yaml`, `/prompts/history_if.yaml`)
- [ ] 시리즈별 자막 스타일·BGM·인트로 차별화

---

## 4. 비용 가드레일 (운영가이드 §3 구체화)

| 항목 | 일일 상한 | 월 예상 (쇼츠 30편 기준) |
| --- | --- | --- |
| OpenAI (스크립트 GPT-4o-mini) | $1 | ~$15 |
| OpenAI (이미지 gpt-image-2 medium, 6장/편) | $1 | ~$9.5 ($0.053 × 6 × 30) |
| Edge-TTS | 무료 | $0 |
| YouTube API | 쿼터 10,000 unit/day | $0 |
| **합계** | — | **~$25–30** |

> **이미지 품질 조절:** `.env`의 `IMAGE_QUALITY=low/medium/high`로 비용 조절 가능.
> DALL-E 3는 2026-05-12부로 API 종료됨.

### 업그레이드 옵션 — AI 동영상 전환 (검토 중)

현재 정적 이미지 대신 Kling AI로 실제 움직이는 영상 클립 생성 가능.

| 방식 | 편당 | 월 8편 기준 |
| --- | --- | --- |
| 현재 (gpt-image-2 정적) | ~$0.32 | ~$2.56 (약 3,800원) |
| Kling AI (AI 영상) | ~$0.75 | ~$6 (약 9,000원) |

→ 월 차이 약 **5천원**. 퀄리티 확인 후 전환 결정 예정.

### 자동 차단 로직
- `daily_cost.py` 워커가 매일 자정 OpenAI usage API 호출 → 임계치 초과 시 `jobs` 큐 일시 정지

---

## 5. 디스크/메모리 관리 정책 (170GB 환경 필수)

- 모든 임시 파일은 `/tmp/aitheater/<job_id>/` → 작업 완료 또는 실패 후 **24시간 내 자동 삭제** (cron)
- 최종 mp4는 YouTube 업로드 성공 시 즉시 삭제, Postgres엔 YouTube ID만 남김
- 배경 소스 캐시 풀 상한: **20GB** (LRU 정책)
- `docker system prune -af --volumes` 주 1회 cron

---

## 6. 보안 체크리스트 (가이드 §2 운영판)

- [ ] `.env`는 `.gitignore` 최상단, pre-commit에 `gitleaks` 훅
- [ ] Slack Signing Secret 검증 **모든 엔드포인트에서**
- [ ] YouTube OAuth scope: `youtube.upload` + `youtube.force-ssl` (댓글 읽기용) **만**
- [ ] Postgres 비밀번호는 Docker secrets로, 환경변수 평문 노출 X
- [ ] 로컬 개발 ngrok 터널은 **수동 종료 습관화** (방치 금지)

---

## 7. 클라우드 이전 트리거 (언제 노트북에서 떠날까)

다음 중 **2개 이상** 해당 시 VPS로 이전:
- 일 자동 발행 편수 ≥ 3편
- 동시 채널 ≥ 2개
- 렌더링 중 MacBook 발열로 작업 지장
- 노트북 들고 외출이 잦아 24/7 운영 불가능

**추천 이전 타깃:** Hetzner CPX31 (4 vCPU / 8GB / €13/mo) 또는 Oracle Cloud ARM Ampere A1 (4 vCPU / 24GB 무료) — Docker Compose 그대로 이식 가능

---

## 📌 즉시 다음 액션 (이번 주)
1. Docker Desktop 대신 **OrbStack** 설치 (메모리 절약)
2. `git init` 이미 되어있으니 → 디렉토리 구조 스캐폴딩 (`api/`, `worker/`, `docker-compose.yml`)
3. OpenAI 키 발급 + `.env.example` 작성
4. **흥부전 Ep.01 수동 1편 만들기** — Phase 1의 핵심 의식
