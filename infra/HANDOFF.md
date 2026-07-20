# AIoT infrastructure handoff

이 문서는 다음 인프라 담당자가 현재 상태에서 바로 작업을 이어가기 위한 기준 문서다.
완료된 항목과 설계만 존재하는 항목을 반드시 구분해서 읽는다.

- 기준일: 2026-07-20 (Asia/Seoul)
- 저장소: `https://lab.ssafy.com/s15-webmobile3-sub1/S15P11E103.git`
- 인프라 작업 브랜치: `infra/dev`
- 기준 인프라 커밋: `d00a09d chore(infra): bootstrap single-EC2 CI/CD`
- EC2 접속 호스트: `ubuntu@i15e103.p.ssafy.io`
- SSH 개인 키: `I15E103T.pem`을 별도 전달받아 사용하며 저장소에 넣지 않는다.
- GPU 서버: `http://70.12.130.103`, 계정 `i15e103`, 할당 장치 `Device3`

## 1. 한눈에 보는 현재 상태

현재 단계는 **단일 EC2의 CI/CD 실행 기반과 MySQL/MQTT 운영 기반까지 완료**된 상태다.
Frontend와 Backend의 실제 애플리케이션 배포, 앱용 HTTPS 라우팅, Jetson 부팅형 Pull OTA는 아직 완료되지 않았다.

| 항목 | 상태 | 비고 |
| --- | --- | --- |
| GitLab Runner | 완료 | Project Runner `#1934`, Online, Shell executor |
| CI 인프라 검증 | 완료 | Pipeline `#154891` 최종 Passed |
| MySQL 8.4 | 완료 | `aiot-mysql`, healthy, 호스트 포트 미공개 |
| 보안 MQTT | 완료 | `aiot-mosquitto`, 인증 필수, 외부 TLS 8883 |
| 일일 로컬 백업 | 완료 | `aiot-backup.timer`, 매일 03:30 KST |
| Frontend 컨테이너 | 미완료 | `frontend/Dockerfile` 필요 |
| Backend 컨테이너 | 미완료 | `backend/Dockerfile`과 health endpoint 필요 |
| 앱용 Nginx HTTPS | 미완료 | 템플릿만 설치됨. 현재 443 listener 없음 |
| Jetson TLS 8883 전환 | 미완료 | 기존 익명 1883 broker를 병행 유지 중 |
| Jetson Pull OTA | 설계 반영, 미구현 | 승인된 버전을 부팅 시 확인·설치하도록 추가 예정 |
| 외부 백업 | 미완료 | 현재 백업은 같은 EC2 디스크에만 존재 |

중요: 현재 `develop` 자동 배포 job은 두 애플리케이션 Dockerfile이 없으면 성공 코드로 종료한다.
따라서 현재 Pipeline 성공은 웹/WAS가 실제 배포됐다는 뜻이 아니다.

## 2. 프로젝트와 인프라 원칙

이 프로젝트는 Jetson Orin Nano에서 ROS2, 센서 처리, 라인트레이싱 상위 제어와 AI 추론을 수행한다.
EC2는 사용자 웹, Spring API, 데이터 저장, MQTT 중계와 CI/CD를 담당한다.

- AI 추론은 EC2나 GPU 서버의 온라인 API가 아니라 Jetson 온디바이스에서 수행한다.
- GPU 서버 Device3는 모델 학습·변환용이며 운영 요청을 직접 처리하지 않는다.
- Jetson은 MySQL에 직접 접근하지 않는다.
- 사용자와 Jetson은 Backend API 또는 MQTT를 통해서만 서버 데이터에 접근한다.
- Jenkins, AWS IoT Core, RDS, ECR은 현재 구조에서 사용하지 않는다.
- WEB/WAS/DB는 논리적으로 분리하되 시간과 운영 비용을 줄이기 위해 한 EC2에 배치한다.

## 3. 목표 런타임 구조

```text
GitLab
  └─ MR/Push
       └─ EC2 GitLab Runner (Shell, concurrent=1)
            ├─ test/validate
            └─ local Docker build + Compose deploy

사용자 브라우저
  └─ HTTPS 443
       └─ Host Nginx
            ├─ /      -> 127.0.0.1:3000 -> aiot-frontend
            └─ /api/  -> 127.0.0.1:8080 -> aiot-backend
                                               ├─ aiot-mysql:3306
                                               └─ aiot-mosquitto:1883

Jetson Orin Nano
  ├─ MQTT TLS -> i15e103.p.ssafy.io:8883 -> aiot-mosquitto
  ├─ HTTPS    -> /api/ -> aiot-backend
  └─ 부팅 시 승인된 Jetson release 확인 -> 필요할 때만 Pull OTA

GPU 서버 Device3
  └─ 모델 학습/변환 -> 승인된 Jetson release의 모델 artifact
```

현재는 위 구조 중 Runner, MySQL, Mosquitto만 실제 가동 중이다.
Nginx는 기존 기본 사이트의 80 포트를 유지하며 앱용 443 설정은 아직 활성화하지 않았다.

## 4. EC2에 실제 배포된 구성

### 4.1 호스트 서비스

| 서비스 | 포트 | 상태/정책 |
| --- | ---: | --- |
| Nginx | 80 | 기존 기본 사이트 유지. 앱 활성화 전까지 수정하지 않음 |
| GitLab Runner | - | `gitlab-runner.service` active |
| Gerrit | 8988, 29418 | 이 프로젝트 외부 서비스. 절대 수정하지 않음 |
| Apache/httpd | 8989 | 이 프로젝트 외부 서비스. 절대 수정하지 않음 |

### 4.2 Docker 컨테이너

| 컨테이너 | 포트 | 상태/정책 |
| --- | --- | --- |
| `aiot-mysql` | Docker 내부 3306 | healthy, 외부 미공개 |
| `aiot-mosquitto` | 내부 1883, 외부 TLS 8883 | 가동 중, 익명 접속 금지 |
| `hanbakwi-mosquitto` | 외부 1883 | 기존 Jetson 마이그레이션용 임시 유지 |
| `aiot-frontend` | loopback 3000 예정 | 아직 없음 |
| `aiot-backend` | loopback 8080 예정 | 아직 없음 |

모든 신규 애플리케이션 컨테이너는 외부 Docker network `aiot-network`를 사용한다.
MySQL은 절대로 호스트의 3306 포트로 publish하지 않는다.

### 4.3 서버 경로

| 경로 | 용도 |
| --- | --- |
| `/srv/aiot/compose` | 운영 Compose 파일 |
| `/srv/aiot/config` | Nginx, Mosquitto 설정 |
| `/srv/aiot/certs/mqtt` | Mosquitto용 인증서 사본 |
| `/srv/aiot/data/mysql` | MySQL 영속 데이터 |
| `/srv/aiot/data/mosquitto` | MQTT 영속 데이터 |
| `/srv/aiot/data/uploads` | Backend 업로드 파일 |
| `/srv/aiot/data/maps` | 지도 파일 |
| `/srv/aiot/secrets` | 운영 비밀값. 출력·커밋 금지 |
| `/srv/aiot/deploy` | 배포·검사·롤백 스크립트와 상태 |
| `/srv/aiot/backups/runtime` | 일일 로컬 백업 |

운영 비밀 파일은 다음과 같다. 값은 어떤 문서나 CI 로그에도 복사하지 않는다.

- `/srv/aiot/secrets/runtime.env`
- `/srv/aiot/secrets/backend.env`
- `/srv/aiot/secrets/robot-mqtt.env`

`robot-mqtt.env`는 Jetson 계정과 접속 위치가 확정된 뒤 인증된 경로로만 전달한다.

## 5. 기존 서비스와 백업 경계

인프라 구축 중 기존 Gerrit, Apache/httpd, Nginx와 익명 Mosquitto를 보존했다.
다음 경계를 지킨다.

- Gerrit의 8988/29418과 Apache의 8989를 중지하거나 설정 변경하지 않는다.
- 앱 준비 전 Nginx 기본 사이트를 교체하지 않는다.
- Jetson TLS 8883 통신 검증 전 `hanbakwi-mosquitto`를 중지하지 않는다.
- Docker publish 포트는 UFW만으로 차단됐다고 판단하지 말고 AWS Security Group도 확인한다.

확인된 백업:

- 정상 pre-infra backup: `/srv/aiot/backups/pre-infra/20260720-025209`
- 검증된 runtime backup: `/srv/aiot/backups/runtime/20260720-033609`
- 부분 생성 디렉터리: `/srv/aiot/backups/pre-infra/20260720-025150`

부분 생성 디렉터리는 내용 검토 없이 복구에 사용하거나 삭제하지 않는다.
현재 백업은 같은 EC2 디스크에 있으므로 인스턴스·볼륨 장애는 보호하지 못한다.

## 6. GitLab Runner와 CI/CD 상태

### 6.1 Runner

- GitLab CE: 18.11.5
- GitLab Runner: 18.11.4
- Project Runner: `#1934 aiot-ec2-runner`
- Tag: `aiot-ec2`
- Executor: Shell
- Global concurrent: 1
- Runner limit: 1
- Request concurrency: 1
- Maximum job timeout: 1800초
- Run untagged jobs: Off
- Lock to current projects: On
- Protected: Off — 파트 dev 브랜치에서도 실행해야 하기 때문

Runner의 Docker group 권한은 사실상 EC2 root 권한과 같다.
프로젝트 멤버를 신뢰된 팀원으로 제한하고 `.gitlab-ci.yml`과 `infra/**` 변경은 인프라 리뷰를 거친다.

Runner 패키지는 GitLab 서버와 같은 18.11 계열로 고정했으며 `gitlab-runner`와 helper image 패키지를 hold했다.

### 6.2 현재 CI job

| Job | 역할 |
| --- | --- |
| `runner_smoke` | Git, Java 21, Node 20, Docker, Compose 확인 |
| `infra_validate` | Shell 문법 및 두 Compose 파일 렌더링 검사 |
| `frontend_ci` | npm install/ci, lint, test, build |
| `backend_ci` | Java 21에서 Gradle/Maven test |
| `iot_ci` | `robot/**` Python compile 검사 |
| `ai_ci` | `ai/**` Python compile 검사 |
| `deploy_develop` | `develop` 자동 EC2 앱 배포 |
| `deploy_master` | `master` 수동 EC2 앱 배포 |

IoT/AI의 현재 검사는 문법 수준이다. 의존성 설치, 단위 테스트, Jetson 하드웨어 테스트는 아직 추가되지 않았다.

### 6.3 EC2 애플리케이션 배포 방식

Docker Registry를 사용하지 않고 EC2 Runner workspace에서 직접 빌드한다.

```text
develop 반영
  -> test/validate
  -> aiot-frontend:<commit-sha-12> build
  -> aiot-backend:<commit-sha-12> build
  -> 이전 compose/env 보관
  -> docker compose up -d
  -> infrastructure + application health check
  -> 성공: history.log 기록
  -> 실패: 이전 compose/env로 자동 rollback
```

동시 배포는 GitLab `resource_group`과 EC2의 `flock`으로 이중 차단한다.
Backend 기본 readiness fallback은 `/swagger-ui.html`이다. Spring Actuator 추가 후 `/actuator/health`로 바꾼다.

## 7. 브랜치 운영 방식과 현재 주의점

최종 선택한 흐름은 파트별 master가 아니라 공용 `develop`과 `master`를 사용하는 방식이다.

```text
feature -> front/dev --\
feature -> back/dev  ---\
feature -> iot/dev   ----> develop --자동 앱 배포--> master --수동 앱 배포
feature -> ai/dev    ---/
feature -> infra/dev --/
```

파트별 소유 경로:

- Frontend: `frontend/**`
- Backend: `backend/**`
- IoT: `robot/**`
- AI: `ai/**`
- Infra: `infra/**`, `.gitlab-ci.yml`, `.env.example`

Git은 소유 경로를 강제하지 않는다. 팀 규칙, protected branch, CODEOWNERS 또는 리뷰 규칙으로 보완해야 한다.

### 7.1 현재 원격 브랜치 상태

- `infra/dev`: 인프라와 `.gitlab-ci.yml`이 존재한다.
- `back/dev`: Spring 초기 프로젝트가 존재한다.
- `front/dev`, `iot/dev`, `ai/dev`, `develop`, `master`: 아직 인프라 CI 파일이 없다.
- `front/master`, `back/master`, `iot/master`, `ai/master`: 현재 CI/CD 흐름에서 사용하지 않는다.

따라서 `.gitlab-ci.yml`이 있는 현재 브랜치는 `infra/dev`뿐이며, 다른 파트 브랜치에서는 아직 CI가 실행되지 않는다.

### 7.2 다음 작업자가 가장 먼저 할 브랜치 작업

1. `infra/dev -> develop` MR을 만들고 병합한다.
2. `develop -> front/dev`, `develop -> back/dev`, `develop -> iot/dev`, `develop -> ai/dev`를 한 번씩 동기화한다.
3. 기존 feature branch는 최신 파트 dev를 merge/rebase한 뒤 MR한다.
4. 이후 기능 branch는 최신 `파트/dev`에서 생성한다.
5. 파트 dev와 develop/master의 direct push를 막고 MR을 사용한다.

위 동기화 전에는 다른 파트가 코드를 push해도 현재 CI 설정이 자동으로 나타나지 않는다.

## 8. 각 파트가 Infra에 제공해야 할 계약

Infra 담당자는 애플리케이션 실행 방식을 추측해서 만들지 않는다.
각 파트가 실행 가능한 형식과 정보를 제공하고 Infra가 이를 공통 CI/CD에 연결한다.

### 8.1 Frontend

- `frontend/package.json`과 lock file
- 사용할 Node 버전. 현재 서버 기준 Node 20
- lint, test, build 명령
- 빌드 산출물 경로
- `frontend/Dockerfile`
- 컨테이너 내부 서비스 포트
- `/` readiness 확인 방법
- Backend API base URL 주입 방식

### 8.2 Backend

- Gradle/Maven wrapper
- Java 버전. 현재 프로젝트와 서버 기준 Java 21
- test와 실행 명령
- `backend/Dockerfile`
- 컨테이너 포트 8080
- `/actuator/health` 또는 합의된 readiness endpoint
- MySQL, MQTT, JWT, CORS 환경변수 목록
- 업로드/지도 저장 경로
- Flyway migration 실행 정책

Backend는 Docker network에서 `aiot-mysql:3306`과 `aiot-mosquitto:1883`을 사용한다.
비밀번호와 JWT secret은 `/srv/aiot/secrets/backend.env`에서 주입한다.

### 8.3 IoT

- `robot/**` 실제 코드와 의존성 파일
- JetPack 6.2에서 사용할 ROS2 배포판과 패키지 목록
- 설치 명령과 launch 명령
- 장치 권한, udev, 카메라/LiDAR device path
- 정상 실행을 판단할 health 또는 heartbeat 방식
- MQTT topic/QoS/reconnect 규칙
- HTTP 업로드 API와 파일 형식
- 로컬 데이터 및 로그 경로

### 8.4 AI

- `ai/**` 실제 코드와 의존성 파일
- 학습 코드와 Jetson 추론 코드의 경계
- GPU 서버 Device3에서 학습·변환하는 명령
- 모델 원본, ONNX, TensorRT engine 등 artifact 종류
- JetPack/CUDA/cuDNN/TensorRT 호환 버전
- 모델 입력/출력 규격과 전처리·후처리 버전
- 모델 health/smoke test 명령
- Jetson에서 실행할 진입점

TensorRT engine은 JetPack/TensorRT/장치 호환성이 강하므로 manifest의 호환 조건 없이 자동 교체하지 않는다.

### 8.5 Infra

- `.gitlab-ci.yml`과 `infra/**` 관리
- 공통 버전과 빌드 명령 반영
- 운영 secret과 인증서 관리
- Compose, Nginx, health check, rollback, backup 관리
- AWS Security Group 확인
- Jetson release packaging과 Pull OTA 골자 관리

## 9. Jetson Pull OTA 계획

### 9.1 현재 상태

Jetson 자동 업데이트는 아직 구현되지 않았다.
현재 `.gitlab-ci.yml`은 AI/IoT 코드를 검사할 뿐 package 생성, registry publish, Jetson 설치를 수행하지 않는다.

목표는 merge마다 Jetson에 push하는 방식이 아니라 **승인된 release만 Jetson이 부팅할 때 가져오는 Pull 방식**이다.

### 9.2 권장 흐름

```text
AI/IoT 코드 push 및 MR 검증
  -> 통합 버전 선택
  -> jetson-vX.Y.Z tag 또는 manual publish job
  -> CI가 release bundle + manifest + SHA256 생성
  -> GitLab Generic Package Registry에 publish

Jetson 부팅
  -> network-online 대기
  -> remote stable manifest 조회
  -> local VERSION과 비교
  -> 같음: 현재 release 실행
  -> 다름: 임시 경로에 다운로드
  -> checksum/호환성/smoke test
  -> versioned release 경로에 설치
  -> current symlink 원자적 전환
  -> ROS2/AI 서비스 시작
  -> 실패: 이전 symlink로 rollback
  -> 네트워크 없음: 기존 정상 버전 실행
```

merge 자체는 release가 아니다. `jetson-v*` tag 또는 승인된 manual job만 stable manifest를 갱신한다.

### 9.3 권장 release 구성

AI와 IoT의 호환성을 보장하기 위해 초기에는 하나의 통합 Jetson release로 관리한다.

```text
aiot-jetson-vX.Y.Z.tar.gz
  robot/
  ai/
  models/
  scripts/install.sh
  scripts/smoke-test.sh
  requirements/
  VERSION
  manifest.json
```

예시 manifest 필드:

```json
{
  "release": "jetson-v0.1.0",
  "robot_commit": "<git-sha>",
  "ai_commit": "<git-sha>",
  "model_version": "<model-version>",
  "jetpack": "6.2",
  "artifact_url": "<private-package-url>",
  "sha256": "<artifact-sha256>",
  "published_at": "<iso-8601>"
}
```

### 9.4 Jetson 측 권장 경로와 서비스

```text
/opt/aiot/
  releases/<version>/
  current -> releases/<version>
  previous -> releases/<previous-version>
  state/VERSION
  secrets/package-read.env
  bin/aiot-update
```

예정 systemd unit:

- `aiot-update.service`: boot 시 한 번 실행하는 updater
- `aiot-update.timer`: 필요할 때만 사용하는 선택적 주기 검사
- `aiot-robot.service`: updater 이후 ROS2/AI 실행

권장 dependency:

```text
network-online.target
  -> aiot-update.service
       -> aiot-robot.service
```

업데이트 실패나 GitLab 접속 실패가 로봇 기동을 막지 않도록 마지막 정상 버전 실행을 fallback으로 둔다.

### 9.5 OTA 보안 조건

- 개인 GitLab 계정 토큰을 Jetson에 저장하지 않는다.
- `read_package_registry` 수준의 Jetson 전용 read-only Deploy Token을 사용한다.
- 토큰은 `/opt/aiot/secrets`에 0600으로 저장하고 저장소·로그에 출력하지 않는다.
- HTTPS와 SHA256 검증은 필수다.
- 가능하면 이후 manifest 또는 artifact signature 검증을 추가한다.
- 업데이트는 순찰 중이 아니라 부팅 또는 명시적인 maintenance 상태에서만 수행한다.
- 다운로드 중 전원이 꺼져도 `current` symlink가 손상되지 않도록 임시 경로와 atomic rename을 사용한다.

### 9.6 OTA 구현을 위해 추가할 파일과 CI

예정 파일:

```text
infra/jetson/aiot-update.sh
infra/jetson/aiot-update.service
infra/jetson/aiot-robot.service
infra/jetson/manifest.schema.json
infra/scripts/package-jetson-release.sh
```

예정 CI job:

- `jetson_validate`: 의존성·manifest·smoke test
- `jetson_package`: release bundle과 checksum 생성
- `jetson_publish`: `jetson-v*` tag 또는 manual 승인 시 registry publish

실제 AI/IoT 코드, 설치 명령, 모델 위치와 실행 entrypoint가 올라온 뒤 위 파일을 최종 구현한다.

## 10. 다음 작업 우선순위

### P0 — 즉시 해야 함

1. `infra/dev -> develop` 병합
2. `develop`을 각 파트 dev에 동기화
3. protected branch와 MR 규칙 적용
4. 각 파트가 실제 코드와 실행 계약을 push
5. `.gitlab-ci.yml`을 실제 버전·빌드 명령에 맞게 조정

### P1 — EC2 앱 배포 완성

1. Frontend/Backend Dockerfile 확보
2. Backend health endpoint 확보
3. `develop` 첫 실제 자동배포
4. 3000/8080이 loopback에만 bind됐는지 확인
5. `/srv/aiot/deploy/install-nginx.sh` 실행
6. HTTPS `/infra-health`, `/`, `/api/` 확인
7. 실패 배포와 rollback 시험

### P2 — Jetson 통신과 Pull OTA

1. Jetson에서 새 MQTT 계정과 TLS 8883 연결
2. command/status/reconnect/heartbeat 시험
3. HTTP 사진·JSON 업로드 E2E 시험
4. Jetson release 형식과 manifest 확정
5. GitLab Package Registry publish CI 추가
6. Jetson updater와 systemd unit 설치
7. 최신/동일/오프라인/손상 artifact/rollback 시나리오 시험
8. 성공 후 기존 `hanbakwi-mosquitto` 중지 및 외부 1883 제거

### P3 — 운영 보완

1. AWS Security Group에서 22, 443, 8883 source 범위 확인
2. 3306, 3000, 8080 외부 차단 확인
3. 외부 암호화 백업 대상 추가
4. 로그·디스크·인증서 만료 모니터링
5. wildcard 인증서 수동 갱신 또는 DNS API 자동화

## 11. 인증서와 네트워크 주의사항

현재 wildcard 인증서는 `2026-09-21 04:14:15 UTC`에 만료된다.
Certbot profile이 manual DNS validation을 사용하므로 인증서 발급·갱신 자체는 자동이 아니다.
성공적으로 갱신된 뒤 deploy hook이 Mosquitto에 복사하고 Nginx를 reload한다.

갱신 후 실행:

```bash
sudo /srv/aiot/deploy/sync-certificates.sh
sudo /srv/aiot/deploy/health-check.sh infrastructure
```

권장 Security Group 정책:

| 포트 | 정책 |
| ---: | --- |
| 22 | 팀의 필요한 source만 허용 |
| 80 | HTTPS redirect/health 용도로 필요 시 허용 |
| 443 | 사용자 웹/API 허용 |
| 8883 | Jetson이 사용하는 source 범위로 제한 권장 |
| 1883 | Jetson 전환 후 외부 차단 |
| 3306 | 외부 차단 |
| 3000, 8080 | 외부 차단 |
| 8988, 8989, 29418 | 기존 서비스 정책을 유지하고 임의 변경 금지 |

## 12. 운영 확인 명령

```bash
# 인프라 전체 health
sudo /srv/aiot/deploy/health-check.sh infrastructure

# 컨테이너 상태
sudo docker compose \
  --env-file /srv/aiot/secrets/runtime.env \
  -f /srv/aiot/compose/compose.infrastructure.yaml ps

# 주요 로그
sudo docker logs --tail 100 aiot-mysql
sudo docker logs --tail 100 aiot-mosquitto
sudo journalctl -u gitlab-runner -n 100 --no-pager

# Runner 연결
sudo gitlab-runner verify

# 백업
sudo systemctl start aiot-backup.service
sudo journalctl -u aiot-backup.service -n 100 --no-pager
systemctl list-timers aiot-backup.timer

# 앱 배포 이후 health
sudo /srv/aiot/deploy/health-check.sh application
```

명령 결과에 환경변수나 secret을 출력하는 `cat /srv/aiot/secrets/*` 형태의 점검은 금지한다.

## 13. 완료 기준

### EC2 앱 배포 완료 기준

- Frontend와 Backend image가 commit SHA tag로 빌드된다.
- 두 컨테이너가 재부팅 후에도 정상 복구된다.
- 3000/8080은 외부에서 직접 접근할 수 없다.
- `https://i15e103.p.ssafy.io/`와 `/api/`가 정상이다.
- MySQL migration과 업로드/지도 영속화가 확인된다.
- 실패 배포에서 이전 버전으로 rollback된다.

### Jetson Pull OTA 완료 기준

- 승인되지 않은 merge는 stable release를 변경하지 않는다.
- Jetson이 동일 버전이면 다운로드하지 않는다.
- 새 버전이면 HTTPS로 내려받고 checksum을 검증한다.
- 네트워크가 없어도 마지막 정상 버전으로 기동한다.
- 설치 또는 smoke test 실패 시 이전 버전으로 복구한다.
- AI 모델과 IoT 코드의 호환 버전이 manifest에 기록된다.
- 토큰, 인증서 private key, MQTT 비밀번호가 Git이나 로그에 노출되지 않는다.

## 14. 관련 문서

- [인프라 개요](README.md)
- [운영 Runbook](OPERATIONS.md)
- [GitLab CI 설정](../.gitlab-ci.yml)
- [인프라 Compose](compose/compose.infrastructure.yaml)
- [애플리케이션 Compose](compose/compose.application.yaml)

