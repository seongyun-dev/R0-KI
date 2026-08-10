# R0-Ki 포팅 및 배포 가이드

확인 기준: 2026-08-10

- GitLab: `https://lab.ssafy.com/s15-webmobile3-sub1/S15P11E103.git`
- 운영 서비스: `https://i15e103.p.ssafy.io`
- API 문서: `https://i15e103.p.ssafy.io/swagger-ui.html`
- EC2 접속: `ssh -i I15E103T.pem ubuntu@i15e103.p.ssafy.io`


## 1. 현재 운영 환경

### 1.1 EC2와 배포 도구

| 항목 | 현재 값 |
| --- | --- |
| Docker | 29.1.3 |
| Docker Compose | 2.40.3 |
| GitLab Runner | 18.11.4, Shell executor, 태그 `aiot-ec2` |
| Git | 2.43.0 |
| CI용 Java | OpenJDK 21.0.11 |
| CI용 Node.js / npm | Node.js 20.20.2 / npm 10.8.2 |
| CI용 Python | Python 3.12.3 |
| IDE | 팀 공통 버전 지정 없음. Backend는 JDK 21, Frontend는 Node.js 20을 IDE에 설정 |

Jenkins는 사용하지 않는다. GitLab Runner와 운영 Docker가 같은 EC2에 설치되어 있다.

### 1.2 애플리케이션과 미들웨어

| 구분 | 제품 및 버전 | 실행 위치 | 포트 |
| --- | --- | --- | --- |
| 외부 웹 서버 | Nginx 1.24.0 | EC2 호스트 | 80, 443 |
| 프론트 웹 서버 | Nginx 1.27.5 | `aiot-frontend` 컨테이너 | 호스트 `127.0.0.1:3000` → 컨테이너 80 |
| 프론트 빌드 | Node.js 20, React 18.3.1, Vite 8.1.1 | Docker build stage | 런타임에는 Node.js 없음 |
| JVM | Eclipse Temurin JRE 21.0.11 | `aiot-backend` 컨테이너 | - |
| WAS | Spring Boot 4.1.0, 내장 Tomcat 11.0.22 | `aiot-backend` 컨테이너 | `127.0.0.1:8080` |
| DB | MySQL 8.4.10 | `aiot-mysql` 컨테이너 | `127.0.0.1:3306` |
| MQTT | Eclipse Mosquitto 2.1.2 | `aiot-mosquitto` 컨테이너 | 내부 1883, 외부 TLS 8883 |

Nginx가 HTTPS를 종료하고 `/`는 프론트, `/api`와 Swagger/OpenAPI는 백엔드로 전달한다. 좌표, 장애물, 긴급 알림 등 SSE 경로는 Nginx 버퍼링을 끈 상태다.

```text
사용자 ── HTTPS 443 ──> Host Nginx
                         ├─ /             ──> Frontend :3000
                         ├─ /api          ──> Backend  :8080
                         └─ /swagger-ui   ──> Backend  :8080

Jetson ── MQTT TLS 8883 ──> Mosquitto ── Docker network ──> Backend
Backend ── Docker network ──> MySQL :3306
```

### 1.3 현재 배포본

| 구성요소 | 브랜치 | 커밋 / 버전 |
| --- | --- | --- |
| Frontend | `front/master` | `7031fbc6b3c6` |
| Backend | `back/master` | `56916e58ed7c` |
| MySQL | - | `mysql:8.4` 이미지, 실제 8.4.10 |
| Mosquitto | - | `eclipse-mosquitto:2` 이미지, 실제 2.1.2 |
| Jetson IoT stable | `iot/master` 계열 | `iot-v0.1.10`, JetPack 6.2, aarch64 |

Frontend, Backend, MySQL, Mosquitto 컨테이너는 모두 실행 중이다. `/`, `/infra-health`, `/v3/api-docs`, Jetson stable manifest는 HTTP 200을 확인했다.

## 2. 소스 클론과 브랜치

```bash
git clone https://lab.ssafy.com/s15-webmobile3-sub1/S15P11E103.git
cd S15P11E103
git fetch origin --prune --tags
```

| 브랜치 | 용도 | 운영 반영 |
| --- | --- | --- |
| `front/dev`, `back/dev`, `ai/dev`, `iot/dev` | 파트별 개발 통합 | CI만 실행 |
| `front/master` | 프론트 배포 기준 | push 후 자동 배포 |
| `back/master` | 백엔드 배포 기준 | push 후 자동 배포 |
| `ai/master` | AI 확정 코드 | 학습·변환 job은 수동 |
| `iot/master` | Robot/IoT 확정 코드 | 태그 생성 후 OTA 패키지 게시 |
| `infra/dev` | CI/CD와 운영 설정 | 검증 후 각 배포 브랜치에 반영 |
| `develop` | 파트 버전 통합 확인 | 운영 자동 배포 없음 |
| `master` | 전체 릴리스 기준 | 배포 job 수동 실행 |

파트 작업은 `작업 브랜치 → 파트/dev → 파트/master` 순서로 합친다. `front/master`와 `back/master`는 서로 독립적으로 배포된다.
브랜치마다 포함된 파일 버전이 다르므로 Backend 작업은 `back/*`, Frontend 작업은 `front/*`, 인프라 작업은 `infra/*`를 checkout한 상태에서 진행한다.

## 3. 빌드 방법

### 3.1 Backend

필요 버전은 Java 21, Gradle Wrapper 9.5.1이다.

```bash
git switch back/master
cd backend
chmod +x gradlew
./gradlew --no-daemon clean test
./gradlew --no-daemon bootJar
cd ..

docker build --pull \
  -t aiot-backend:back-$(git rev-parse --short=12 HEAD) \
  backend
```

Dockerfile은 `eclipse-temurin:21-jdk-jammy`에서 JAR를 빌드한 뒤 `eclipse-temurin:21-jre-jammy` 이미지에 복사한다. 결과물은 `/app/app.jar`로 실행된다.

### 3.2 Frontend

필요 버전은 Node.js 20과 npm이다. 의존성은 `package-lock.json`을 기준으로 설치한다.

```bash
git switch front/master
cd frontend
npm ci
npm run lint
npm run build
cd ..

docker build --pull \
  -f infra/docker/frontend.Dockerfile \
  --build-arg VITE_API_BASE_URL= \
  --build-arg VITE_USE_MOCKS=false \
  -t aiot-frontend:front-$(git rev-parse --short=12 HEAD) \
  frontend
```

`VITE_API_BASE_URL`을 비워 두면 브라우저가 현재 도메인의 `/api`를 사용한다. 운영 빌드에서 Mock API는 사용하지 않는다.

### 3.3 통합 확인

Frontend와 Backend 이미지를 함께 띄운 뒤 Nginx, MySQL, MQTT, 회원가입, 로그인, JWT, Robot API를 검사한다.

```bash
export FRONTEND_IMAGE=aiot-frontend:front-<commit>
export BACKEND_IMAGE=aiot-backend:back-<commit>
export INTEGRATION_PROJECT=aiot-manual-check
export INTEGRATION_PORT=19080
bash infra/scripts/integration-test.sh
```

통합 Compose는 별도 네트워크와 임시 MySQL을 사용한다. 운영 DB에는 접근하지 않는다.

## 4. CI/CD와 배포

`.gitlab-ci.yml`의 주요 순서는 다음과 같다.

1. Runner, 셸 스크립트, Compose, 계약 파일 검증
2. 파트별 단위 테스트 및 빌드
3. 커밋 SHA가 포함된 Docker 이미지 생성
4. 현재 운영 중인 반대편 서비스와 후보 이미지 통합 테스트
5. 해당 파트 컨테이너만 교체
6. HTTP, MySQL, MQTT 상태 확인
7. 실패하면 직전 이미지로 자동 롤백
8. 결과를 Mattermost로 전송

이미지 이름은 다음 형식이다.

```text
aiot-frontend:front-<commit 12자리>
aiot-backend:back-<commit 12자리>
```

Frontend와 Backend 이미지는 별도 Registry가 아니라 EC2의 Docker daemon에 저장된다. 새 EC2에서 복구할 때는 GitLab 소스로 이미지를 다시 빌드해야 한다.

운영 배포는 GitLab 파이프라인 사용을 원칙으로 한다. 수동 배포가 필요하면 원하는 파트 코드가 checkout된 저장소에서 실행한다.

```bash
sudo env CI_PROJECT_DIR="$PWD" \
  bash infra/scripts/deploy.sh <branch> <commit-sha> frontend

sudo env CI_PROJECT_DIR="$PWD" \
  bash infra/scripts/deploy.sh <branch> <commit-sha> backend
```

직전 릴리스 또는 특정 이미지로 되돌릴 때는 다음 명령을 사용한다.

```bash
sudo /srv/aiot/deploy/rollback.sh frontend <release-id|image>
sudo /srv/aiot/deploy/rollback.sh backend <release-id|image>
sudo /srv/aiot/deploy/rollback.sh release <release-id>
```

배포 이력은 `/srv/aiot/deploy/release-manifest.json`과 `/srv/aiot/deploy/releases/`에 남는다.

### 4.1 Jetson Robot Pull OTA

Jetson 운영 배포는 승인된 Robot 패키지를 Jetson이 직접 내려받는 Pull OTA를 사용한다.

```text
iot/dev → iot/master → iot-vX.Y.Z 태그
  → iot_package 자동 실행
  → iot_publish 수동 승인
  → GitLab Package Registry에 패키지 저장
  → EC2의 stable manifest 갱신
  → Jetson이 manifest 확인 후 새 버전만 다운로드·설치
```

배포 순서는 다음과 같다.

1. 검증을 마친 Robot 코드를 `iot/master`에 병합한다.
2. `iot/master`에 포함된 커밋으로 `iot-vX.Y.Z` 태그를 만든다.
3. 태그 파이프라인의 `iot_package` 성공을 확인한다.
4. `iot_publish` job을 실행해 stable 버전으로 승인한다.
5. Jetson은 부팅 2분 후, 이후 5분마다 stable manifest를 확인한다.
6. 새 버전이면 호환성, 용량, SHA-256, 내부 checksum과 smoke test를 통과한 뒤 `/opt/aiot/iot/current`를 원자적으로 교체한다.
7. 기존에 실행 중이던 AI → ROS → Robot 서비스 순으로 재시작한다. 검증이나 재시작이 실패하면 `/opt/aiot/iot/previous`로 자동 복구한다.

즉시 확인해야 할 때만 Jetson에서 updater를 한 번 실행한다. 이 명령도 소스를 직접 설치하지 않고 같은 stable manifest를 조회한다.

```bash
sudo systemctl start aiot-update.service
systemctl status aiot-update.service --no-pager
readlink -f /opt/aiot/iot/current
cat /opt/aiot/iot/state/VERSION
```

현재 Jetson은 최초 설치가 끝난 상태이므로 일반 배포 때 설치 스크립트를 다시 실행하지 않는다. Jetson을 새로 설치하거나 초기화한 경우에만 읽기 전용 Package Registry 계정과 환경 파일을 준비한 뒤 `sudo bash infra/jetson/install.sh --enable`을 한 번 실행한다.

IoT 패키지에는 `robot/` 런타임만 포함한다. 기존 AI venv, 모델, TensorRT engine, 로그와 증거 파일은 OTA가 수정하지 않는다.

## 5. 신규 서버 초기 설정

EC2에는 Docker, Docker Compose, Nginx, GitLab Runner, Java 21, Node.js 20이 필요하다. TLS 인증서는 현재 `/etc/letsencrypt/live/p.ssafy.io/` 경로를 사용한다.

```bash
sudo bash infra/scripts/bootstrap-server.sh "$PWD"
sudo /srv/aiot/deploy/initialize-secrets.sh
sudo /srv/aiot/deploy/sync-certificates.sh
sudo /srv/aiot/deploy/deploy-infrastructure.sh
sudo /srv/aiot/deploy/install-nginx.sh
sudo /srv/aiot/deploy/health-check.sh infrastructure
```

초기화 후 `/srv/aiot/secrets/backend.env`에 GMS, 메일, Solapi 값을 추가한다. 이후 Frontend와 Backend는 각 master 파이프라인으로 배포한다.

## 6. 환경변수

### 6.1 GitLab CI/CD 변수

| 변수 | 용도 | 비고 |
| --- | --- | --- |
| `MM_WEBHOOK_URL` | Mattermost 배포 알림 | protected, masked |
| `DEPLOY_FREEZE` | `true`이면 파트 master 자동 배포 중지 | 긴급 동결용 |
| `AI_GPU_SELECTOR` | AI 학습에 사용할 GPU | 기본값 `3`, 가능하면 GPU UUID 사용 |
| `CI_JOB_TOKEN` | IoT 패키지 업로드 | GitLab 기본 제공 |

`FRONTEND_IMAGE`, `BACKEND_IMAGE`, `INTEGRATION_PROJECT`, `INTEGRATION_PORT`는 파이프라인에서 실행마다 만든다.

### 6.2 Frontend 빌드 변수

| 변수 | 운영값 | 설명 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | 빈 문자열 | 동일 도메인의 `/api` 사용 |
| `VITE_USE_MOCKS` | `false` | 운영 Mock 비활성화 |
| `VITE_DEFAULT_MAP_ID` | 기본 `1` | 기본 지도 ID |
| `VITE_DEFAULT_ROBOT_ID` | 기본 `1` | 기본 로봇 ID |
| `VITE_STATS_ENDPOINT` | `/api/statistics` | 통계 API 빌드 인자 |

Vite 변수는 빌드 결과에 포함되므로 비밀번호와 토큰을 넣으면 안 된다.

### 6.3 Backend 런타임 변수

운영값은 `/srv/aiot/secrets/backend.env`에 둔다.

| 구분 | 변수 |
| --- | --- |
| DB | `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD` |
| JWT | `APP_JWT_SECRET`, `APP_JWT_ACCESS_TOKEN_EXPIRATION` |
| CORS/Proxy | `APP_CORS_ALLOWED_ORIGINS`, `SERVER_FORWARD_HEADERS_STRATEGY` |
| MQTT | `MQTT_BROKER_URI`, `MQTT_USERNAME`, `MQTT_PASSWORD` |
| 파일 | `UPLOAD_DIR`, `MAP_DIR` |
| 시간대 | `TZ=Asia/Seoul`, `JAVA_TOOL_OPTIONS=-Duser.timezone=Asia/Seoul` |
| GMS | `GMS_BASE_URL`, `GMS_KEY`, `GMS_MODEL`, `GMS_CHAT_COMPLETIONS_PATH`, `GMS_TIMEOUT_SECONDS` |
| 메일 | `MAIL_USERNAME`, `MAIL_PASSWORD`, 필요 시 `MAIL_HOST`, `MAIL_PORT`, `MAIL_FROM` |
| Solapi | `SOLAPI_API_KEY`, `SOLAPI_API_SECRET`, `SOLAPI_SENDER_NUMBER` |
| 이메일 인증 | `APP_EMAIL_VERIFICATION_ENABLED` |

현재 운영 JWT 만료시간은 `28800000ms`(8시간), GMS 모델은 `gpt-5-mini`, Backend profile은 `mqtt-spike`다. 이메일 인증은 운영 기본값 `true`를 유지한다. 현재 `back/dev`의 통합 테스트 Compose에서만 `false`로 설정한다.

### 6.4 DB와 MQTT 초기 비밀값

`/srv/aiot/secrets/runtime.env`에 다음 값을 둔다.

```text
MYSQL_DATABASE
MYSQL_USER
MYSQL_ROOT_PASSWORD
MYSQL_PASSWORD
MQTT_ROBOT_USERNAME
MQTT_ROBOT_PASSWORD
MQTT_BACKEND_USERNAME
MQTT_BACKEND_PASSWORD
APP_JWT_SECRET
```

이 파일은 `initialize-secrets.sh`가 생성하며 권한은 `0640`, 소유자는 `root:aiot`이다.

### 6.5 Jetson OTA 변수

- `/opt/aiot/secrets/package-read.env`: stable manifest URL, GitLab Package Registry 읽기 전용 계정과 토큰, JetPack·AI 계약 버전
- `/opt/aiot/secrets/robot.env`: Robot Key, MQTT TLS 계정, Backend service token
- `/opt/aiot/secrets/ai.env`: 기존 AI venv, ROS 2 topic, engine 및 evidence 경로
- `/opt/aiot/secrets/ros.env`: LiDAR, RF2O, SLAM/Nav2 실측 설정

`package-read.env`의 Package Registry 토큰은 `read_package_registry` 권한만 부여한다. stable manifest는 `https://i15e103.p.ssafy.io/jetson/releases/iot/stable/manifest.json`에서 확인하며, 패키지 다운로드에만 읽기 전용 토큰을 사용한다.

## 7. DB 접속과 스키마

| 항목 | 값 |
| --- | --- |
| DBMS | MySQL 8.4.10 |
| Database | `aiot` |
| 애플리케이션 계정 | `aiot_app` |
| Backend 접속 주소 | `jdbc:mysql://aiot-mysql:3306/aiot` |
| EC2 내부 점검 주소 | `127.0.0.1:3306` |
| 외부 접속 | 차단 |
| 데이터 경로 | `/srv/aiot/data/mysql` |

비밀번호는 `/srv/aiot/secrets/runtime.env`와 `backend.env`에만 저장한다. MySQL `root`는 초기화와 백업용이고 애플리케이션에서는 사용하지 않는다.

별도 ERD 파일은 없다. 실제 스키마 기준은 다음 Flyway 파일이다.

- 초기 스키마: `backend/src/main/resources/db/migration/V1__create_initial_schema.sql`
- 변경 이력: 같은 디렉터리의 `V2`부터 `V18`까지
- 시연 데이터: `backend/scripts/operational-data-august2026.sql`
- 통계용 더미 데이터: `backend/scripts/stats-dummy-july2026.sql`

Backend 시작 시 Flyway가 미적용 migration을 순서대로 실행한다. 운영 DB에서 migration 파일을 수정하거나 이미 적용된 파일 번호를 재사용하면 안 된다.

서비스 로그인 계정은 DB 초기 SQL에 평문으로 고정하지 않는다. 회원가입 API로 생성하며 시연 계정이 필요하면 별도 보안 채널로 전달한다.

## 8. 주요 계정과 설정 파일

### 8.1 계정

| 계정 | 용도 |
| --- | --- |
| `ubuntu` | EC2 SSH와 운영 점검 |
| `gitlab-runner` | GitLab Shell Runner, 빌드·배포 실행 |
| `aiot_app` | Backend용 MySQL 계정 |
| `root` | MySQL 초기화·백업 전용 |
| `spring-backend` | Backend용 MQTT 계정 |
| `robot-01` | Jetson Robot용 MQTT 계정 |
| `e103` | Jetson 로컬 운영 계정 |

### 8.2 Git에서 관리하는 파일

| 파일 | 내용 |
| --- | --- |
| `.gitlab-ci.yml` | CI/CD job과 브랜치 규칙 |
| `.env.example` | Compose 검증용 예시값, 운영 비밀번호 아님 |
| `backend/src/main/resources/application.yml` | Spring, 메일, GMS, 파일 경로 기본값 |
| `backend/src/main/resources/db/migration/*.sql` | DB 스키마 기준 |
| `infra/compose/compose.application.yaml` | Frontend·Backend 운영 Compose |
| `infra/compose/compose.infrastructure.yaml` | MySQL·Mosquitto 운영 Compose |
| `infra/compose/compose.integration.yaml` | CI 통합 테스트 Compose |
| `infra/nginx/aiot.conf.template` | HTTPS, API, Swagger, SSE, OTA reverse proxy |
| `infra/mosquitto/mosquitto.conf` | MQTT 인증, 내부 1883, 외부 TLS 8883 |
| `infra/scripts/initialize-secrets.sh` | 서버 비밀값 파일 생성 |
| `infra/scripts/deploy.sh` | 부분 배포, health check, manifest 기록 |
| `infra/scripts/rollback.sh` | 파트·릴리스 롤백 |
| `infra/jetson/*.env.example` | Jetson AI와 OTA 설정 예시 |

### 8.3 서버에서만 관리하는 파일

| 파일 | 내용 |
| --- | --- |
| `/srv/aiot/secrets/runtime.env` | MySQL, MQTT, JWT 원본 비밀값 |
| `/srv/aiot/secrets/backend.env` | Backend 런타임 환경변수 |
| `/srv/aiot/secrets/robot-mqtt.env` | Jetson MQTT 접속 정보 |
| `/srv/aiot/config/mosquitto/passwd` | Mosquitto 해시 비밀번호 |
| `/srv/aiot/deploy/current.env` | 현재 Frontend·Backend 이미지와 commit |
| `/srv/aiot/deploy/release-manifest.json` | 마지막 배포 결과 |

## 9. 운영 점검과 특이사항

```bash
curl -fsS https://i15e103.p.ssafy.io/infra-health
curl -fsS https://i15e103.p.ssafy.io/v3/api-docs >/dev/null
sudo /srv/aiot/deploy/health-check.sh application
sudo docker ps
sudo docker logs --tail 100 aiot-backend
```

- MySQL, Frontend, Backend는 호스트 loopback에만 bind되어 외부에서 3000, 3306, 8080으로 직접 접속할 수 없다.
- Git 기준 Mosquitto 외부 포트는 TLS 8883만 필요하다. 현재 EC2 Compose에는 1883 publish가 남아 있어 외부에서도 접속된다. `infra/compose/compose.infrastructure.yaml`과 서버 파일을 동기화한 뒤 1883 publish를 제거해야 한다.
- 일일 백업은 `aiot-backup.timer`가 매일 03:30 KST 실행한다. 7일이 지난 백업은 목록만 출력하고 자동 삭제하지 않는다.
- 저장소에는 `aiot-monitor.timer` 정의가 있지만 현재 EC2에는 unit이 설치되지 않았다. 모니터링을 사용하려면 `bootstrap-server.sh`를 다시 반영하거나 unit을 별도로 설치해야 한다.
- 현재 TLS 인증서 만료일은 2026-09-21이다. 갱신 후 `sync-certificates.sh`로 MQTT 인증서까지 동기화한다.
- EC2에 기존부터 있던 8988, 8989, 29418 포트 서비스는 프로젝트 배포 범위가 아니므로 변경하지 않는다.
