# AIoT Infrastructure Design Document

> **Summary**: 단일 EC2, GitLab Runner, GPU Device3, Jetson Orin Nano를 연결하는 공통 CI/CD·운영·Pull OTA 설계
>
> **Project**: AI 기반 스마트 아파트 순찰 시스템
> **Version**: 1.0.0
> **Author**: Infra
> **Created**: 2026-07-20
> **Status**: Review
> **Level**: Enterprise

---

## Related Documents

- Plan: [aiot-infrastructure.plan.md](../../01-plan/features/aiot-infrastructure.plan.md)
- Handoff: [infra/HANDOFF.md](../../../infra/HANDOFF.md)
- Operations: [infra/OPERATIONS.md](../../../infra/OPERATIONS.md)
- CI: [.gitlab-ci.yml](../../../.gitlab-ci.yml)

## 1. Architecture Overview

### 1.1 Design Goals

1. 애플리케이션 코드가 없어도 smoke fixture로 CI, image build, 배포, 검증, rollback 경로를 재현한다.
2. Frontend와 Backend는 독립적으로 검사·빌드하되 단일 EC2 배포 상태는 하나의 조정된 release로 관리한다.
3. AI와 IoT는 일반 CI와 GPU 작업을 분리하고, 승인된 조합만 Jetson 통합 release로 발행한다.
4. Jetson은 서버가 장비에 push하지 않고 부팅 또는 maintenance 시점에 release를 Pull한다.
5. 기존 Gerrit, Apache, 기본 Nginx와 legacy MQTT를 검증 gate 이전에는 변경하지 않는다.
6. 운영 secret, 인증서 private key, Runner token, Package Registry token을 Git과 CI 로그에서 분리한다.

### 1.2 Constraints and Trade-offs

| Constraint | Decision | Trade-off |
| --- | --- | --- |
| 단일 EC2 | WEB/WAS/DB/MQTT를 논리 분리하고 한 호스트에 배치 | staging/production 물리 격리 없음 |
| EC2 Shell Runner | 로컬 Docker daemon에서 image build·배포 | Runner 권한이 사실상 root 수준 |
| Registry 미사용 EC2 배포 | Frontend/Backend image는 EC2 로컬에 commit tag로 보관 | EC2 손실 시 image 재빌드 필요 |
| 코드 미완성 | 조건부 CI와 격리된 smoke fixture 사용 | 실제 workload 적합성은 별도 검증 필요 |
| Jetson 현장 장비 | Pull OTA, offline fallback, atomic switch | updater와 device test 설계가 필요 |
| GPU Device3 공유 | 학습·변환 job은 manual + resource lock | 완전 자동 학습보다 운영 개입 증가 |
| 기존 서비스 공존 | 포트와 서비스 변경 금지 경계 유지 | Nginx/MQTT 전환을 단계적으로 진행 |

### 1.3 System Context

```text
GitLab
  ├─ MR/Push -> EC2 Runner(aiot-ec2)
  │              ├─ validate/test
  │              ├─ Frontend/Backend image build
  │              └─ EC2 Compose deploy + verify + rollback
  │
  ├─ Manual AI job -> GPU Runner(ai-gpu-device3)
  │                    └─ model train/convert/package
  │
  └─ jetson-vX.Y.Z/manual publish
                     └─ Generic Package Registry + stable manifest

Browser
  └─ HTTPS 443 -> Host Nginx
                    ├─ /      -> 127.0.0.1:3000 -> aiot-frontend:80
                    ├─ /api/  -> 127.0.0.1:8080 -> aiot-backend:8080
                    ├─ /infra-health
                    └─ /jetson/releases/stable/manifest.json

EC2 Docker network: aiot-network
  ├─ aiot-frontend
  ├─ aiot-backend
  ├─ aiot-mysql:3306
  └─ aiot-mosquitto:1883

Jetson Orin Nano (JetPack 6.2)
  ├─ MQTT TLS 8883 -> aiot-mosquitto
  ├─ HTTPS /api/   -> aiot-backend
  └─ HTTPS stable manifest + private artifact -> Pull OTA
```

### 1.4 Service Boundaries

| Component | Responsibility | Runtime |
| --- | --- | --- |
| Host Nginx | TLS 종료, route, upload limit, infra health, stable manifest 제공 | EC2 host |
| Frontend | React SPA | Docker, Nginx static server, internal 80 |
| Backend | REST/WebSocket, auth, DB/MQTT integration | Docker, Java 21, internal 8080 |
| MySQL | 업무 데이터와 Flyway schema | Docker, internal 3306 only |
| Mosquitto | Backend/Jetson 메시지 중계 | Docker, internal 1883 + external TLS 8883 |
| EC2 Runner | CI, local image build, deployment orchestration | EC2 Shell Runner |
| GPU Runner | 학습·변환·모델 smoke | GPU server Device3 |
| Jetson updater | release 조회·검증·설치·rollback | Jetson systemd |
| Robot runtime | ROS2, sensor, AI inference | Jetson systemd 또는 추후 확정된 runtime |

## 2. Repository and Ownership Design

### 2.1 Monorepo Layout

```text
S15P11E103/
  frontend/
    Dockerfile
    .dockerignore
    nginx.conf
  backend/
    Dockerfile
    .dockerignore
  ai/
    scripts/{test,train,convert,smoke-test,run}.sh
  robot/
    scripts/{install,test,smoke-test,run}.sh
  infra/
    compose/
    nginx/
    mosquitto/
    smoke/
    jetson/
    scripts/
    CONTRACTS.md
  .gitlab-ci.yml
```

### 2.2 Ownership

| Path | Primary Owner | Required Review |
| --- | --- | --- |
| `frontend/**` | Frontend | Frontend; Dockerfile은 Infra 추가 |
| `backend/**` | Backend | Backend; Dockerfile/health 계약은 Infra 추가 |
| `ai/**` | AI | AI; packaging/runtime 계약은 Infra 추가 |
| `robot/**` | IoT | IoT; device/OTA 계약은 Infra 추가 |
| `infra/**` | Infra | Infra 필수 |
| `.gitlab-ci.yml` | Infra | Infra 필수 |
| `**/Dockerfile` | Infra + 해당 파트 | 양쪽 승인 |

### 2.3 Branch and Merge Flow

```text
part/feat/* -> part/dev -> develop -> master
```

| Ref | Purpose | Pipeline | Deployment |
| --- | --- | --- | --- |
| feature branch MR | 파트 기능 검증 | 변경 파트 CI | 없음 |
| `front/dev`, `back/dev`, `ai/dev`, `iot/dev`, `infra/dev` | 파트 통합 | 파트 CI | 없음 |
| `develop` | 전체 통합 | 전체 변경 파트 CI | Frontend/Backend 자동 EC2 배포 |
| `master` | 안정 release | 전체 검증 | EC2 수동 배포 |
| `jetson-v*` tag | 승인된 장비 release | Jetson validate/package | Registry publish + stable 갱신 |

공유 브랜치는 protected branch로 설정하고 direct push와 force push를 금지한다. 개인 feature branch는 MR 직전 최신 part/dev로 rebase할 수 있지만 공유 part/dev는 force rebase하지 않는다.

## 3. Platform Contracts

### 3.1 Frontend Contract

| Item | Contract |
| --- | --- |
| Framework | React; 기본 adapter는 Vite |
| Runtime | Node 20 build -> Nginx static runtime |
| Package manager | npm + `package-lock.json` |
| Commands | `npm ci`, lint/test if present, `npm run build` |
| Output | 기본 `dist/`; CRA `build/`는 adapter가 감지 |
| Container port | 80 |
| API | relative `/api` |
| Readiness | `GET /` returns 2xx |

Dockerfile은 multi-stage로 구성한다. Builder가 `dist/` 또는 `build/`를 `/out`에 정규화하고 runtime Nginx가 `/out`만 복사한다. SPA route는 `try_files $uri $uri/ /index.html`로 처리한다.

### 3.2 Backend Contract

| Item | Contract |
| --- | --- |
| Runtime | Java 21 |
| Build | Gradle Wrapper, `test`, `bootJar` |
| Artifact | executable Spring Boot JAR |
| Container port | 8080 |
| Readiness | `/actuator/health`; 초기 `/swagger-ui.html` fallback |
| DB | `jdbc:mysql://aiot-mysql:3306/...` |
| MQTT | `tcp://aiot-mosquitto:1883` |
| Migration | Flyway forward-only |
| Persistent paths | `/app/data/uploads`, `/app/data/maps` |

Dockerfile은 JDK builder와 JRE runtime의 multi-stage로 구성한다. Runtime은 non-root UID를 사용하고 JVM option은 `JAVA_TOOL_OPTIONS`로 주입한다.

### 3.3 AI/IoT Interface Contract

실제 framework에 종속되지 않도록 Infra는 다음 실행 인터페이스만 강제한다.

| Script | Responsibility |
| --- | --- |
| `scripts/test.sh` | CPU에서 가능한 test/static validation |
| `scripts/install.sh` | release staging 경로에 의존성 설치 |
| `scripts/run.sh` | 운영 진입점 |
| `scripts/smoke-test.sh` | 짧고 결정적인 정상 판정 |
| `ai/scripts/train.sh` | GPU manual training |
| `ai/scripts/convert.sh` | ONNX/TensorRT 등 artifact 변환 |

스크립트가 아직 없으면 CI는 Python compile 수준으로 동작하고 계약 파일이 추가된 시점부터 해당 스크립트를 필수로 전환한다.

## 4. EC2 Runtime Design

### 4.1 Host Paths

```text
/srv/aiot/
  compose/
  config/{nginx,mosquitto}/
  certs/mqtt/
  data/{mysql,mosquitto,uploads,maps}/
  deploy/
    current.env
    previous.env
    current-compose.yaml
    previous-compose.yaml
    history.log
    deploy.lock
  releases/jetson/stable/
  secrets/{runtime.env,backend.env,robot-mqtt.env}/
  backups/runtime/
  logs/
```

### 4.2 Docker Network and Ports

| Service | Docker Port | Host Binding | External Access |
| --- | ---: | --- | --- |
| Frontend | 80 | `127.0.0.1:3000` | Nginx 443 only |
| Backend | 8080 | `127.0.0.1:8080` | Nginx `/api/` only |
| MySQL | 3306 | none | prohibited |
| Mosquitto internal | 1883 | none | Backend only |
| Mosquitto TLS | 8883 | `0.0.0.0:8883` | Jetson source restricted |

모든 신규 container는 external Docker network `aiot-network`에 연결한다. Docker publish port가 UFW를 우회할 수 있으므로 Security Group을 최종 통제 지점으로 본다.

### 4.3 Nginx Routes

| Route | Target | Availability |
| --- | --- | --- |
| `/infra-health` | Nginx static 200 | 항상 |
| `/` | Frontend `127.0.0.1:3000` | Frontend enabled 후 |
| `/api/` | Backend `127.0.0.1:8080` | Backend enabled 후 |
| `/jetson/releases/stable/manifest.json` | EC2 static manifest | stable publish 후 |

앱 준비 전에도 TLS와 `/infra-health`는 검증할 수 있다. 준비되지 않은 upstream은 503 maintenance response로 처리하거나 route를 활성화하지 않는다.

### 4.4 Secret Model

| File | Consumer | Permission |
| --- | --- | --- |
| `runtime.env` | Infra Compose/health/backup | `root:aiot 0640` |
| `backend.env` | Backend container | `root:aiot 0640` |
| `robot-mqtt.env` | Jetson 전달용 | `root:aiot 0640` |
| Jetson package token | Jetson updater | `/opt/aiot/secrets 0600` |

secret 값은 GitLab variable 또는 서버 파일로만 전달한다. job에서 `set -x`, 전체 env 출력, secret 파일 `cat`을 금지한다.

## 5. CI/CD Architecture

### 5.1 Pipeline Stages

```text
validate -> test -> build -> package -> deploy -> verify
```

| Stage | Jobs | Result |
| --- | --- | --- |
| validate | runner_smoke, infra_validate, contract_validate | 도구·문법·Compose·계약 검증 |
| test | frontend_ci, backend_ci, ai_ci, iot_ci | 파트별 test |
| build | frontend_image, backend_image | local Docker image with commit tag |
| package | jetson_validate, jetson_package | versioned bundle/checksum |
| deploy | deploy_develop, deploy_master, jetson_publish | EC2 또는 Registry 반영 |
| verify | verify_ec2, verify_release | health/manifest/rollback evidence |

### 5.2 Conditional Execution

- `rules:changes`로 파트 경로와 CI/Infra 변경을 감지한다.
- `rules:exists`로 필수 manifest를 확인한다.
- 코드가 없는 파트는 skip하지만 코드가 존재하고 계약 파일이 빠진 경우 명확히 fail한다.
- `infra/**` 또는 `.gitlab-ci.yml` 변경은 모든 관련 validation을 실행한다.

| Part | Availability Gate |
| --- | --- |
| Frontend | `frontend/package.json` + lock file |
| Backend | `backend/gradlew` + Gradle build file |
| AI | Python/manifest/requirements 중 하나 |
| IoT | Python/ROS2 manifest 중 하나 |

### 5.3 Image Naming

```text
aiot-frontend:<CI_COMMIT_SHA first 12>
aiot-backend:<CI_COMMIT_SHA first 12>
```

`latest`는 배포 기준으로 사용하지 않는다. 배포 상태에는 component별 image와 source commit을 함께 기록한다.

### 5.4 Component-aware Deployment

CD job은 하나를 유지하고 component 상태만 독립적으로 갱신한다.

```text
current.env 읽기
  -> 새 frontend image 존재: FRONTEND_IMAGE/COMMIT 갱신
  -> 새 backend image 존재: BACKEND_IMAGE/COMMIT 갱신
  -> 이전 component 값은 유지
  -> target service만 compose up -d
  -> infrastructure + deployed component health
  -> 성공: current state와 history 기록
  -> 실패: previous state/compose로 rollback
```

`resource_group: aiot-ec2-deploy`와 `/srv/aiot/deploy/deploy.lock`의 `flock`을 함께 사용한다. 첫 배포에서도 Backend만 준비됐으면 Backend만 기동할 수 있어야 한다.

### 5.5 Deployment State

`current.env`는 단일 EC2의 release manifest 역할을 한다.

```dotenv
DEPLOY_BRANCH=develop
DEPLOY_COMMIT=<integration-commit>
FRONTEND_ENABLED=true
FRONTEND_IMAGE=aiot-frontend:<sha>
FRONTEND_COMMIT=<sha>
BACKEND_ENABLED=true
BACKEND_IMAGE=aiot-backend:<sha>
BACKEND_COMMIT=<sha>
FRONTEND_HEALTH_URL=http://127.0.0.1:3000/
BACKEND_HEALTH_URL=http://127.0.0.1:8080/actuator/health
```

파일은 temporary file 작성 후 `mv`로 원자 교체한다. `history.log`에는 secret 없이 timestamp, branch, integration commit, component image만 기록한다.

### 5.6 Environment Strategy

물리 EC2가 한 대이므로 `develop`과 `master`는 서로 다른 동시 환경이 아니다.

- 개발 기간: `develop`을 공유 integration environment로 자동 배포
- 시연/최종 release: 배포 freeze 후 `master`를 수동 배포
- master 배포는 같은 EC2를 안정 조합으로 덮어쓴다.
- 별도 staging이 필요해지면 두 번째 EC2 또는 분리된 hostname/port/Compose project가 선행돼야 한다.

## 6. Data Architecture

### 6.1 Persistence

| Data | Path | Backup |
| --- | --- | --- |
| MySQL | `/srv/aiot/data/mysql` | consistent mysqldump |
| MQTT persistence | `/srv/aiot/data/mosquitto` | tar + checksum |
| Uploads | `/srv/aiot/data/uploads` | tar + checksum |
| Maps | `/srv/aiot/data/maps` | tar + checksum |
| Deployment state | `/srv/aiot/deploy/*.env`, history | backup copy |
| Jetson local state | `/opt/aiot/releases`, `state/VERSION` | previous release retained |

### 6.2 Migration Strategy

- Flyway는 Backend 시작 시 적용한다.
- migration은 기존 application version과 가능한 한 하위 호환되게 작성한다.
- 자동 application rollback이 DB schema를 자동 복원하지 않는다.
- destructive migration은 사전 backup, maintenance 승인, forward correction 절차를 요구한다.
- 동일 migration version 변경을 금지하고 새 migration으로 수정한다.

### 6.3 Retention

| Item | Initial Retention |
| --- | --- |
| Local runtime backup | 7일, 자동 삭제 전 dry-run/검증 |
| External encrypted backup | 최소 14일, 대상 확정 후 적용 |
| Docker images | current + previous + 최근 성공 3개 |
| Deployment history | 프로젝트 종료까지 |
| Jetson releases | current + previous + 최근 성공 1개 추가 |
| Container logs | size-based rotation, service별 5 files |

## 7. API and Messaging Contracts

### 7.1 HTTP Infrastructure Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/infra-health` | none | Nginx/TLS liveness |
| GET | `/` | application | Frontend readiness |
| GET | `/api/actuator/health` 또는 agreed health | none/limited | Backend readiness |
| GET | `/jetson/releases/stable/manifest.json` | none | stable release pointer |

Private artifact는 공개 manifest와 별개로 GitLab read-only Deploy Token을 요구한다.

### 7.2 MQTT Topic Contract

초기 권장 namespace는 다음과 같다.

```text
aiot/robots/{robotId}/commands
aiot/robots/{robotId}/status
aiot/robots/{robotId}/heartbeat
aiot/robots/{robotId}/events
```

| Topic | Direction | QoS | Retain |
| --- | --- | ---: | --- |
| commands | Backend -> Jetson | 1 | no |
| status | Jetson -> Backend | 1 | yes |
| heartbeat | Jetson -> Backend | 0 | no |
| events | Jetson -> Backend | 1 | no |

대용량 이미지·지도 파일은 MQTT payload에 넣지 않고 HTTPS API로 전송한다. 최종 payload schema는 Backend/IoT 계약과 함께 확정한다.

## 8. GPU and Model Pipeline

### 8.1 Runner Design

권장안은 GPU 서버에 별도 GitLab Runner를 설치하는 것이다.

- Runner tag: `ai-gpu-device3`
- project locked: on
- untagged jobs: off
- concurrency: 1
- GPU resource group: `ai-gpu-device3`
- training job: manual, non-interruptible 기본
- 개인 SSH password/token을 CI 변수로 중계하는 방식은 사용하지 않는다.

GPU 서버에 Runner 설치 권한이 없을 때만 제한된 SSH dispatch를 대안으로 검토한다.

### 8.2 AI Jobs

| Job | Runner | Trigger | Output |
| --- | --- | --- | --- |
| `ai_ci` | EC2 | MR/push | test result |
| `ai_train` | GPU | manual | checkpoint/model |
| `ai_convert` | GPU | manual/needs train | ONNX/TensorRT artifact |
| `ai_model_publish` | GPU/EC2 | approved manual | versioned package + checksum |

### 8.3 Model Manifest

```json
{
  "model_version": "parking-v1",
  "source_commit": "<sha>",
  "format": "onnx",
  "sha256": "<sha256>",
  "architecture": "aarch64",
  "jetpack": "6.2",
  "cuda": "<detected>",
  "tensorrt": "<detected-or-null>",
  "input_spec": {},
  "output_spec": {},
  "preprocess_version": "<version>",
  "postprocess_version": "<version>"
}
```

CUDA/TensorRT 값은 추측하지 않고 GPU/Jetson에서 탐지한 값을 release gate로 사용한다.

## 9. Jetson Pull OTA Design

### 9.1 Release Artifact

```text
aiot-jetson-vX.Y.Z.tar.gz
  robot/
  ai/
  models/
  requirements/
  scripts/install.sh
  scripts/smoke-test.sh
  VERSION
  manifest.json
```

### 9.2 Release Manifest

```json
{
  "schema_version": 1,
  "release": "jetson-v0.1.0",
  "robot_commit": "<sha>",
  "ai_commit": "<sha>",
  "model_version": "<version>",
  "jetpack": "6.2",
  "architecture": "aarch64",
  "artifact_url": "<private-gitlab-package-url>",
  "sha256": "<artifact-sha256>",
  "published_at": "<iso-8601>"
}
```

### 9.3 Device Layout

```text
/opt/aiot/
  releases/<version>/
  current -> releases/<version>
  previous -> releases/<previous-version>
  state/VERSION
  secrets/package-read.env
  bin/aiot-update
  logs/
```

### 9.4 Update State Machine

```text
START
  -> wait network-online with bounded timeout
  -> fetch stable manifest
     -> network/API failure: RUN_CURRENT
  -> compare VERSION
     -> same: RUN_CURRENT
  -> validate schema/JetPack/architecture/free disk
     -> incompatible: RUN_CURRENT + report failure
  -> download to .staging
  -> verify SHA256
     -> fail: remove staging, RUN_CURRENT
  -> extract versioned directory
  -> install + pre-activation smoke
     -> fail: remove new release, RUN_CURRENT
  -> atomically move current to previous and activate new current
  -> start robot runtime + bounded post-activation health
     -> fail: restore previous, restart previous
  -> persist VERSION and prune old releases
```

### 9.5 Atomic Switch

- release는 완성될 때까지 `.staging/<version>`에 둔다.
- `releases/<version>` 이동이 완료된 뒤 symlink를 새 temporary name으로 생성한다.
- `mv -T`로 `current` symlink를 원자 교체한다.
- 설치 중 전원이 끊겨도 기존 `current`를 변경하지 않는다.

### 9.6 systemd Ordering

```text
network-online.target
  -> aiot-update.service
       -> aiot-robot.service
```

- updater는 network 실패를 application fatal로 취급하지 않는다.
- `aiot-robot.service`는 update 완료 후 시작하지만 update network failure 때문에 차단되지 않는다.
- maintenance 중이 아닌 주기적 업데이트는 기본 비활성화한다.
- 장치 권한은 최소한의 `dialout`, `video` 등 실제 요구 group으로 제한한다.

### 9.7 Release Channel

- versioned artifact는 GitLab Generic Package Registry에 publish한다.
- stable manifest는 CI가 EC2의 `/srv/aiot/releases/jetson/stable/manifest.json`에 temporary file 후 atomic replace한다.
- Nginx는 manifest만 HTTPS로 공개한다.
- artifact 다운로드는 Jetson 전용 `read_package_registry` Deploy Token을 사용한다.
- stable 갱신은 `jetson-v*` tag 또는 protected manual job에서만 가능하다.

## 10. Security Architecture

### 10.1 Trust Boundaries

| Boundary | Control |
| --- | --- |
| Internet -> Nginx | TLS 1.2/1.3, only 80/443 |
| Jetson -> MQTT | TLS 8883, username/password, source restriction |
| Backend -> MySQL/MQTT | private Docker network |
| GitLab -> EC2 Runner | project-locked tagged Runner |
| GitLab -> GPU Runner | protected manual job, device resource lock |
| Jetson -> Package Registry | read-only Deploy Token |

### 10.2 Security Group Policy

| Port | Policy |
| ---: | --- |
| 22 | 필요한 관리 source만 |
| 80 | redirect/infra health에 필요할 때 |
| 443 | 사용자와 Jetson HTTPS |
| 8883 | Jetson source 범위 |
| 1883 | TLS 전환 후 외부 차단 |
| 3306, 3000, 8080 | 외부 차단 |
| 8988, 8989, 29418 | 기존 정책 유지; Infra 변경 금지 |

### 10.3 Supply Chain

- base image는 최소 minor version으로 고정하고 운영 전 digest pin을 검토한다.
- image와 Jetson artifact는 source commit과 SHA256을 기록한다.
- dependency audit는 경고와 blocking threshold를 분리한다.
- CI script 변경은 Infra 승인과 protected branch를 요구한다.
- private key와 token은 artifact, cache, Docker build context에 포함하지 않는다.

## 11. Observability and Operations

### 11.1 Logging

- Docker `json-file` size rotation을 유지한다.
- application은 stdout/stderr structured log를 사용한다.
- 배포 로그는 secret 없이 `/srv/aiot/deploy/history.log`에 기록한다.
- Jetson updater는 release, phase, result만 기록하고 token URL header는 기록하지 않는다.

### 11.2 Health and Metrics

| Check | Interval/Trigger | Failure Condition |
| --- | --- | --- |
| MySQL container health | deploy + periodic | unhealthy |
| MQTT authenticated round-trip | deploy + periodic | publish/sub timeout |
| Frontend HTTP | deploy | non-2xx |
| Backend readiness | deploy | non-2xx/timeout |
| Disk | periodic | >= 80% warning, >= 90% critical |
| Backup freshness | daily | last success > 26h |
| Certificate | daily | < 21 days warning, < 14 days critical |
| Jetson heartbeat | Backend monitoring | agreed timeout exceeded |

초기에는 heavyweight Prometheus/ELK를 필수로 하지 않고 systemd timer, health script, Docker logs로 운영한다. 프로젝트 규모가 커지면 metrics exporter와 Grafana를 추가한다.

### 11.3 Alerts

알림 transport는 팀이 선택한 Slack/Discord/메일 webhook으로 추상화한다. secret webhook은 서버 secret 파일 또는 protected CI variable로 저장한다.

## 12. Performance and Capacity

- EC2 Runner concurrency는 1로 유지해 build와 deploy 충돌을 막는다.
- build와 deploy가 application 자원을 압박할 수 있으므로 시연·운영 시간대에는 deployment freeze를 사용할 수 있다.
- MySQL, Backend, Frontend에 명시적 memory/resource limit은 실제 workload 관측 후 설정한다.
- upload 최대 크기는 Nginx 200 MiB로 시작하고 실제 사진 규격 확정 후 낮춘다.
- Backend/Frontend readiness timeout은 각각 최대 150초, 150초 범위에서 현재 script와 맞춘다.
- MQTT message에는 대용량 binary를 넣지 않는다.

## 13. Rollback and Recovery

### 13.1 Application Rollback

- current/previous env와 Compose를 deployment 직전에 보관한다.
- 새 container가 기동하고 health를 통과한 뒤 성공으로 기록한다.
- 실패 시 previous image 조합으로 `compose up -d`하고 health를 재검증한다.
- 첫 단독 component 배포 실패 시 해당 service만 제거하고 infra service는 유지한다.

### 13.2 Database Recovery

- application rollback과 DB rollback을 결합하지 않는다.
- DB 복구는 검증된 backup과 checksum을 선택한 명시적 수동 절차다.
- 복구 전 현재 DB의 추가 snapshot/dump를 만든다.

### 13.3 Jetson Recovery

- current/previous symlink로 software rollback한다.
- network 실패 시 current를 그대로 실행한다.
- current 자체가 손상됐으면 previous를 시도한다.
- 두 release 모두 실패하면 장비가 명확한 failure state와 로컬 진단 로그를 남긴다.

## 14. File-level Implementation Map

### 14.1 Modify

| File | Change |
| --- | --- |
| `.gitlab-ci.yml` | build/package/verify stage, conditional jobs, Jetson/GPU jobs 추가 |
| `infra/compose/compose.application.yaml` | component-aware deployment와 runtime health 계약 반영 |
| `infra/nginx/aiot.conf.template` | SPA/API/infra-health/stable manifest/maintenance 처리 |
| `infra/scripts/deploy.sh` | component 독립 build/state 갱신/first deploy 지원 |
| `infra/scripts/health-check.sh` | component 선택 검증, evidence 출력 |
| `infra/scripts/rollback.sh` | component state와 첫 배포 rollback 보강 |
| `infra/scripts/backup.sh` | metadata, freshness, retention gate 보강 |
| `infra/OPERATIONS.md` | 신규 CI/CD·GPU·OTA 운영 절차 반영 |
| `infra/HANDOFF.md` | 구현 진척과 실제 검증 결과 반영 |

### 14.2 Add

| File | Purpose |
| --- | --- |
| `infra/CONTRACTS.md` | 파트별 입력·출력·명령·포트 계약 |
| `infra/smoke/frontend/**` | React/Nginx 배포 배관 fixture |
| `infra/smoke/backend/**` | Backend health 배관 fixture |
| `frontend/Dockerfile`, `.dockerignore`, `nginx.conf` | 실제 React image contract |
| `backend/Dockerfile`, `.dockerignore` | 실제 Spring image contract |
| `infra/jetson/aiot-update.sh` | Pull updater |
| `infra/jetson/aiot-update.service` | boot update unit |
| `infra/jetson/aiot-robot.service` | runtime unit |
| `infra/jetson/manifest.schema.json` | release schema validation |
| `infra/scripts/package-jetson-release.sh` | versioned bundle/checksum 생성 |
| `infra/scripts/monitor-health.sh` | periodic disk/backup/cert/container check |
| `infra/GPU_RUNNER.md` | Device3 Runner 설치·운영 절차 |

실제 Frontend/AI/IoT 파트 디렉터리에 파일을 추가할 때는 해당 파트 최신 branch와 MR을 사용해 소유권 충돌을 피한다.

## 15. Implementation Order

### Phase A - Platform Ready

1. `infra/CONTRACTS.md`와 smoke fixture
2. CI stages와 조건부 job
3. component-aware deploy state/health/rollback
4. Nginx HTTPS `/infra-health`
5. smoke build/deploy/failure rollback evidence

### Phase B - Frontend/Backend Onboarding

1. Backend Dockerfile과 actual back/dev integration
2. Backend 단독 배포와 readiness
3. Frontend 코드 반영 후 React Dockerfile adapter 확정
4. 두 component 통합 배포와 HTTPS `/`, `/api/`

### Phase C - GPU/Jetson Delivery

1. GPU 환경 탐지와 Runner 설치
2. AI manual train/convert/package
3. Jetson package script/manifest schema
4. updater/systemd 설치
5. 정상/동일/오프라인/손상/rollback test

### Phase D - Operational Ready

1. Jetson TLS MQTT E2E 후 legacy 1883 제거
2. Security Group 검증
3. monitoring/alert
4. external backup/restore drill
5. Runbook와 completion report

## 16. Test Plan

### 16.1 Static and CI Tests

- 모든 Shell file `bash -n`; 가능하면 ShellCheck
- Compose config render
- Nginx config test
- Frontend install/lint/test/build
- Backend Gradle test/bootJar
- Python compile + 파트 test script
- manifest JSON Schema validation
- secret signature scan

### 16.2 EC2 Integration Tests

| Scenario | Expected Result |
| --- | --- |
| Infra-only pipeline | app deploy 없이 명확히 skip |
| Backend-only first deploy | Backend만 기동, infra 유지 |
| Frontend add | Frontend 기동, Backend image 유지 |
| Backend update | Backend만 교체, Frontend 유지 |
| Health failure | previous component 조합 복구 |
| Host reboot | enabled container와 timer 복구 |
| External port scan | 3306/3000/8080 차단 |

### 16.3 Jetson OTA Tests

| Scenario | Expected Result |
| --- | --- |
| 동일 버전 | 다운로드 없음 |
| 새 정상 버전 | checksum/smoke 후 current 전환 |
| 네트워크 없음 | current 실행 |
| manifest 불일치 | update 거부, current 실행 |
| checksum 불일치 | staging 제거, current 실행 |
| smoke 실패 | new release 폐기, previous/current 유지 |
| activation 후 runtime 실패 | previous rollback |
| update 중 전원 중단 | 기존 current 손상 없음 |

### 16.4 Recovery Drills

- application first deploy failure
- application previous image rollback
- verified MySQL dump restore in isolated target
- certificate renewal and Mosquitto/Nginx reload
- Jetson previous release recovery

## 17. Acceptance Gates

| Gate | Required Before |
| --- | --- |
| Platform smoke pass | develop automatic deployment enable |
| Backend health contract pass | Backend production-like deployment |
| Frontend build output confirmed | Frontend actual image adoption |
| GPU environment detected | TensorRT artifact automation |
| Jetson access and current runtime backup | updater installation |
| TLS MQTT E2E pass | legacy 1883 shutdown |
| External backup pass | destructive data migration |

## 18. Version History

| Version | Date | Changes | Author |
| --- | --- | --- | --- |
| 1.0.0 | 2026-07-20 | Initial enterprise infrastructure design | Infra |
