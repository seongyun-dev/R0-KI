# AI — 엣지 비전 & 서버 인사이트

R0-Ki의 AI는 두 층으로 나뉩니다.

1. **엣지 비전** (Jetson): YOLO 탐지 + 번호판 OCR → ROS로 Robot 런타임에 전달
2. **서버 LLM** (Backend): 순찰 요약·주/월 통계 인사이트 (GMS Chat Completions)

이 폴더(`ai/`)는 주로 **학습 산출물·지표 문서**를 둡니다. 실시간 추론 파이프라인 본체는 Jetson 쪽 서비스이며, 레포의 Robot 어댑터(`robot/src/aiot_robot/`)가 ROS 계약으로 연결합니다.

루트 프로젝트 설명: [../README.md](../README.md)

---

## 구성

```text
ai/
├── Yolo/          # 탐지 체크포인트·지표·예시 이미지
├── Ocr/           # 번호판 인식 파인튜닝 산출물·지표
├── Report/        # 리포트/프롬프트 참고용 (서버 LLM 입력은 Backend가 생성)
└── CONTRIBUTING.md
```

| 문서 | 내용 |
| --- | --- |
| [Yolo/README.md](Yolo/README.md) | 체크포인트 버전, 권장 가중치 |
| [Yolo/docs/models.md](Yolo/docs/models.md) | mAP·클래스·데이터셋 |
| [Ocr/README.md](Ocr/README.md) | OCR 산출물 경로 |
| [Ocr/docs/models.md](Ocr/docs/models.md) | Acc 정의·학습 요약 |
| [robot/docs/ai-ros-contract-v1.md](../robot/docs/ai-ros-contract-v1.md) | Robot↔AI ROS 계약 |
| [backend/README.md](../backend/README.md) | GMS 워커·인사이트 API |

---

## 엣지 비전

### YOLO 탐지

- 베이스: **YOLO26n** 전이학습
- 권장 가중치: `Yolo/checkpoints/v3/best.pt`
- 검증 지표(요약): **mAP50 ≈ 0.86** (상세·클래스별은 [Yolo/docs/models.md](Yolo/docs/models.md))

| id | class |
| --- | --- |
| 0 | small_trash |
| 1 | standing |
| 2 | sitting |
| 3 | lying |
| 4 | bin_overflow |
| 5 | bin_normal |
| 6 | bag_outside |
| 7 | licence |

### 번호판 OCR

- 베이스: `korean_PP-OCRv5_mobile_rec` 파인튜닝
- 산출물: `Ocr/models/ocr_finetune_rec/`
- 검증(요약): 라인 **완전일치 Acc ≈ 0.93** ([Ocr/docs/models.md](Ocr/docs/models.md))

탐지 bbox의 `licence` 영역 크롭 → OCR → (데모/파이프라인에 따라) 트랙 단위 다수결.

### Robot 연동 원칙

```text
카메라 → YOLO(+OCR) → evidence 저장
  → /ai/detections (ROS)
  → Robot DetectionRecorder + outbox
  → POST /api/robot/events | /vehicle-checks
```

ROS 토픽 (요약):

| 토픽 | 방향 | 역할 |
| --- | --- | --- |
| `/ai/control` | Robot → AI | ENABLE / DISABLE |
| `/ai/status` | AI → Robot | heartbeat, READY 게이트 |
| `/ai/detections` | AI → Robot | 탐지 + evidence 경로 |

- AI 프로세스가 죽어도 Robot의 MQTT·STOP·안전 제어는 유지
- AI 미준비 시 순찰은 LIMITED 등 fail-closed 정책 (IoT README 참고)
- `bin_overflow` / `bag_outside` 등은 프레임 단위로 이벤트 타입으로 **collapse**
- **차량 불법 여부는 엣지에서 확정하지 않음** — Backend가 주차 구역·등록 차량으로 판정

어댑터·outbox: `robot/src/aiot_robot/` (`ai_runtime.py`, `ai_adapter_core.py`, `event_delivery.py`)

엣지 엔진 경로(TensorRT/ONNX 등)는 Jetson 설정(`robot/roki/config/ai.yaml` 등)에서 관리하며, 자격증명·장비 전용 경로는 Git에 넣지 않습니다.

---

## 서버 LLM

RAG는 사용하지 않습니다. Backend가 DB 집계로 **마크다운 표** 또는 **순찰 JSON**을 만들고 GMS에 전달합니다.

| 기능 | 흐름 |
| --- | --- |
| 주/월 인사이트 | 통계 표 → `AnalyticsInsightWorker` → 저장 → FE 폴링 |
| 순찰 요약 | `PatrolCompletedEvent` → `PatrolAiSummaryWorker` |

프롬프트는 추측·개인정보 노출·정책 제안을 제한하도록 Backend `GmsClient` 쪽에 정의됩니다. API 키·베이스 URL은 환경 변수만 사용합니다.

Frontend: `frontend/src/features/stats/` (`useAnalyticsInsight`, `InsightReportPanel`)

---

## 포트폴리오 포인트

1. 단지 순찰 도메인에 맞춘 **8클래스 전이학습** 탐지
2. 번호판 **Detect → OCR** 파이프라인과 검증 Acc 정의(완전일치)
3. 프로세스 분리 + **ROS 계약**으로 Robot 안전 루프와 AI 수명주기 분리
4. 불법주차는 비전만으로 단정하지 않는 **책임 분리**
5. LLM은 원시 로그가 아닌 **집계 표**로 환각·토큰을 억제
