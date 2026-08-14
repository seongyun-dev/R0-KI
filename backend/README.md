# Backend — oneloop

아파트 순찰 로봇 관제 API 서버입니다. 관리자 웹(Frontend)과 Jetson 로봇(IoT)을 REST·MQTT·SSE로 연결하고, 탐지 이벤트·순찰·통계·AI 요약/인사이트·SMS를 처리합니다.

루트 프로젝트 설명: [../README.md](../README.md)

---

## 기술 스택

| 영역 | 선택 |
| --- | --- |
| 프레임워크 | Spring Boot 4.1, Java 21 |
| API | Spring WebMVC, springdoc OpenAPI |
| 영속성 | Spring Data JPA, Flyway, MySQL (테스트 H2) |
| 보안 | Spring Security, JWT(jjwt), 로봇 서비스 토큰 |
| IoT | Eclipse Paho MQTT |
| 실시간 | SSE (`SseEmitter`) |
| AI | GMS Chat Completions (OpenAI 호환) — 설정은 환경 변수 |
| SMS | Solapi SDK — 자격증명은 환경 변수 |
| 기타 | Spring Mail, openhtmltopdf, Lombok, Spotless |

앱 진입점: `com.oneloop.OneloopApplication`

---

## 실행

```bash
cd backend
./gradlew bootRun
# Windows: gradlew.bat bootRun
```

- 로컬 DB·MQTT·메일·GMS·SMS 등은 **환경 변수 / 로컬 설정**으로만 주입합니다.
- 시크릿·실서버 주소·토큰 값을 README나 Git에 넣지 않습니다.
- API 문서: 서버 기동 후 Swagger UI (`/swagger-ui.html` 등 springdoc 기본 경로)

테스트:

```bash
./gradlew test
```

---

## 패키지 구조

```text
com.oneloop/
├── auth / member     # 가입·로그인·이메일 인증
├── apartment         # 단지
├── robot             # 로봇 CRUD·텔레메트리·스트림·SSE
├── map / mapping     # 지도·존·웨이포인트·맵핑 세션
├── patrol            # 순찰·PDF·AI 요약 워커
├── event             # 탐지 이벤트·증거·로봇 REST·SSE
├── resident          # 입주민·차량
├── notification      # SMS 알림
├── analytics         # 통계·AI 인사이트
├── mqtt              # 인바운드/퍼블리시
└── global            # security, gms, sms, async, exception, file
```

계층: `controller` → `service` → `repository` / `domain`, 비동기 작업은 `event` + Worker.

---

## 인증

| 주체 | 방식 | 용도 |
| --- | --- | --- |
| 관리자 | JWT Bearer | `/api/**` 관제·CRUD |
| 로봇 | 로봇 서비스 토큰 (`ROLE_ROBOT`) | `/api/robot/**` 이벤트·차량 체크 등 |

필터: `JwtAuthenticationFilter`, `RobotTokenAuthenticationFilter` — `SecurityConfig`에서 경로별 분리.

---

## API prefix (요약)

| Prefix | 역할 |
| --- | --- |
| `/api/auth` | signup, email, signin, me |
| `/api/robots` | 로봇 CRUD, 위치/장애물 SSE, 스트림 세션 |
| `/api/robot` | 로봇 전용 이벤트·배치·vehicle-checks |
| `/api/events` | 목록/상세/상태, 긴급·일반 SSE, evidence |
| `/api/patrols` | 시작/중지, 목록/상세, PDF |
| `/api/map` | 지도·파일·활성화, zones, waypoints |
| `/api/map/mapping-sessions` | 맵핑 시작/중지 + SSE |
| `/api/residents` | 입주민·차량 |
| `/api/notifications` | 알림 조회 |
| `/api/analytics/events` | overview, trend, by-type, by-zone, handling |
| `/api/analytics/insights` | 주/월 AI 인사이트 |
| `/api/internal/stream-sessions` | 스트림 세션 검증 |

상세 스키마는 Swagger를 참고하세요.

---

## 핵심 로직

### 1. MQTT ↔ 도메인 ↔ SSE

```text
Robot pose/status/ack
  → MqttInboundHandler
  → RobotTelemetryService (및 맵핑 ACK 처리)
  → ApplicationEvent (AFTER_COMMIT)
  → SSE 서비스 → Frontend
```

명령 방향:

```text
Frontend REST (순찰/맵핑)
  → Service
  → MqttPublisher → hanbakwi/v1/robots/{robotKey}/command
```

### 2. AFTER_COMMIT + Async Worker

DB에 작업 상태를 남긴 뒤, 커밋 이후에만 외부 I/O를 수행합니다. 전용 Executor로 풀을 분리합니다 (`AsyncConfig`).

| 이벤트 | 워커 | 목적 |
| --- | --- | --- |
| `AnalyticsInsightRequestedEvent` | `AnalyticsInsightWorker` | 통계 표 → GMS → 인사이트 저장 |
| `PatrolCompletedEvent` | `PatrolAiSummaryWorker` | 순찰 요약 |
| `NotificationRequestedEvent` | `NotificationWorker` | SMS |
| `EmergencyEventCreatedEvent` 등 | SSE Listener | 실시간 푸시 |

인사이트 API는 캐시된 `COMPLETED`면 즉시 반환하고, 아니면 `PENDING`/`PROCESSING`을 돌려 Frontend가 폴링합니다.

### 3. 로봇 탐지 이벤트

`RobotEventController` → `EventCreationService`:

- 응급 단건 / 쓰레기 등 배치
- 차량: 엣지는 탐지·번호판만 → Backend가 구역·등록 차량으로 판정
- 증거 업로드, 체크포인트 매칭, 알림 연동

### 4. 맵핑 세션

`MappingSessionController`: 시작/중지 MQTT 명령 + ACK 상태 머신 + 세션 SSE.

### 5. 순찰 워치독·PDF

연결 끊김 감시(`PatrolConnectionWatchdog`), 순찰 리포트 PDF 생성.

---

## 대표 시퀀스

### 텔레메트리 → 관제

```text
MQTT pose → Telemetry → RobotLocationUpdatedEvent
  → AFTER_COMMIT → Robot SSE → FE 지도 핀 갱신
```

### 인사이트 생성

```text
GET /api/analytics/insights
  → PENDING upsert + AnalyticsInsightRequestedEvent
  → 즉시 PENDING/PROCESSING 응답
  → AFTER_COMMIT → analyticsInsightExecutor
  → 마크다운 표 빌드 → GMS → COMPLETED/FAILED
```

입력은 통짜 로그가 아니라 **집계 마크다운 표** 위주여서 토큰·환각을 줄입니다. 모델명·API 키는 설정/환경 변수에만 둡니다.

---

## DB

- Flyway: `src/main/resources/db/migration/` (`ddl-auto: validate`)
- 도메인: 멤버, 단지, 로봇, 맵/존/웨이포인트, 순찰, 이벤트, 입주민, 알림, 인사이트 등

---

## 관련 코드 경로

- MQTT: `.../mqtt/MqttPublisher.java`, `MqttInboundHandler.java`, `MqttConfig.java`
- 인사이트: `.../analytics/event/AnalyticsInsightRequestedEvent.java`, `AnalyticsInsightWorker.java`
- 보안: `.../global/security/`
- GMS: `.../global/gms/client/GmsClient.java` (프롬프트·호출만, 키는 설정)
