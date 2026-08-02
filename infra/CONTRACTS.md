# AIoT 구성요소 실행 계약

이 문서는 각 파트가 공통 CI/CD에 연결되기 위해 지켜야 하는 최소 실행 계약이다.
애플리케이션 기능은 각 파트가 소유하고, 빌드·실행·배포 인터페이스는 Infra와 함께 관리한다.

## 공통 규칙

- 파트 코드는 지정된 최상위 디렉터리 안에 둔다.
- secret, 인증서 private key, 장비 credential을 Git에 저장하지 않는다.
- CI에서 사용할 설치·검사·빌드 명령은 비대화형으로 종료돼야 한다.
- Docker image는 commit SHA tag를 사용하고 `latest`를 배포 기준으로 사용하지 않는다.
- `.gitlab-ci.yml`, `infra/**`, `**/Dockerfile` 변경은 Infra 리뷰를 거친다.
- 코드가 없는 파트의 CI job은 skip한다. 코드가 있는데 계약 파일이 빠진 경우에는 fail한다.

## 프론트엔드

| Item | Contract |
| --- | --- |
| Path | `frontend/` |
| Framework | React; 기본 build adapter는 Vite |
| Runtime | Node 20 build, Nginx static runtime |
| Package manager | npm |
| Required files | `package.json`, `package-lock.json`, `Dockerfile` |
| Install | `npm ci` |
| Lint | `npm run lint --if-present` |
| Test | `npm run test --if-present` |
| Build | `npm run build` |
| Output | 기본 `dist/`; CRA는 `build/` adapter 허용 |
| Container port | 80 |
| API base | 동일 origin의 `/api` |
| Readiness | `GET /` returns 2xx |

운영 도메인이나 Backend IP를 소스에 하드코딩하지 않는다. React Router를 사용하면 Nginx SPA fallback을 유지한다.

## 백엔드

| Item | Contract |
| --- | --- |
| Path | `backend/` |
| Runtime | Java 21 |
| Build tool | Gradle Wrapper |
| Required files | `gradlew`, `build.gradle` 또는 `build.gradle.kts`, `Dockerfile` |
| Test | `./gradlew --no-daemon test` |
| Build | `./gradlew --no-daemon bootJar` |
| Container port | 8080 |
| Readiness | 최종 `/actuator/health`; 초기 `/swagger-ui.html` fallback |
| Database | `aiot-mysql:3306`, Flyway forward migration |
| MQTT | `aiot-mosquitto:1883` |
| Runtime timezone | `Asia/Seoul` (container `TZ`, JVM `user.timezone`) |
| Persistent paths | `/app/data/uploads`, `/app/data/maps` |

비밀 운영 설정은 `/srv/aiot/secrets/backend.env`에서 환경변수로 주입한다. 시각대처럼 비밀이 아닌 공통 런타임 설정은 Compose가 고정한다. DB migration은 애플리케이션 image rollback과 자동으로 되돌리지 않는다.

## AI

| Item | Contract |
| --- | --- |
| Current runtime | `/home/e103/yolo-pipeline` |
| Python | existing Python 3.10 venv with system site packages |
| Service | `aiot-ai.service` |
| Runtime entrypoint | `python -m yolo_pipeline.main` after ROS Humble setup |
| Local ROS | `ROS_LOCALHOST_ONLY=1`, `ROS_DOMAIN_ID=0` |
| Status | `/ai/status`, reliable/volatile, 2-second heartbeat |
| Control | `/ai/control`, reliable/transient-local |
| Detections | `/ai/detections`, reliable/volatile |
| Evidence | `/var/lib/aiot/evidence` |
| Operations readiness | `/run/aiot/ai-ready.json` after a READY heartbeat |
| Source workspace | `ai/` for training/model assets until runtime migration |
| CPU test | `ai/scripts/test.sh` when provided |
| GPU training | `ai/scripts/train.sh` |
| Model conversion | `ai/scripts/convert.sh` |
| Training output | `ai/artifacts/training/` |
| Converted models | `ai/artifacts/converted/` |
| Model metadata | version, source commit, format, checksum, input/output spec |

AI는 Backend URL, MQTT credential, robot service token을 소유하지 않는다. 외부 통신은
Robot이 담당한다. GPU 학습·변환은 protected manual job에서만 실행하며 현재 AI
baseline과 TensorRT engine은 IoT OTA가 수정하지 않는다.

## IoT / Robot

| Item | Contract |
| --- | --- |
| Path | `robot/` |
| ROS metadata | `package.xml`, `CMakeLists.txt` 또는 Python dependency manifest |
| Install | `robot/scripts/install.sh` |
| Test | `robot/scripts/test.sh` |
| Runtime smoke | `robot/scripts/smoke-test.sh` |
| Runtime entrypoint | `robot/scripts/run.sh` |
| AI contract | `robot/docs/ai-ros-contract-v1.md` |
| Limited mode | stale/not-ready AI status rejects patrol without killing Robot |
| Device requirements | udev rule, group, camera/LiDAR path를 문서화 |

장비 경로와 계정값을 소스에 하드코딩하지 않는다. 사진·지도처럼 큰 payload는 MQTT가 아니라 HTTPS API를 사용한다.

## Jetson IoT 릴리스

IoT release에는 Robot 코드만 포함하며 AI runtime과 모델은 포함하지 않는다.

```text
aiot-iot-vX.Y.Z.tar.gz
  robot/
  scripts/install.sh
  scripts/smoke-test.sh
  VERSION
  manifest.json
  CHECKSUMS.sha256
```

일반 merge는 stable release를 변경하지 않는다. `iot/master`에 포함된 commit의 protected
`iot-vX.Y.Z` tag와 수동 `iot_publish` 승인만 허용한다. Manifest의
`required_ai_contract_version`으로 고정 AI runtime과의 ROS JSON 호환성을 확인한다.
외부 stable manifest는 실제 archive SHA256과 크기를 기록한다.

## 브랜치 흐름

```text
feature -> part/dev -> part/master -> develop -> root master
```

- feature와 part/dev: 해당 파트 CI만 수행하고 배포하지 않는다.
- front/master와 back/master: 후보 통합검사 후 해당 파트만 EC2에 자동 배포한다.
- develop: 이미 배포 성공한 파트 release 조합을 검증·기록하며 EC2를 변경하지 않는다.
- root master: 검증된 최종 마일스톤을 같은 EC2에 수동 배포한다.
- Jetson: 별도 tag/manual release만 Package Registry에 발행한다.
