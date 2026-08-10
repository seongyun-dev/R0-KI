# Jetson AI 서비스와 Robot Pull OTA

Jetson에서는 AI와 Robot을 의도적으로 분리해 관리한다.

```text
/home/e103/yolo-pipeline
  └─ 기존 AI 기준선, aiot-ai.service가 실행

/opt/aiot/iot/releases/*
  └─ Robot 전용 iot-v* 릴리스, aiot-update.service가 갱신
```

IoT OTA는 AI venv, `*.pt`, `*.onnx`, `*.engine`, AI 로그와 evidence를 포함하거나 변경하지 않는다. AI와 Robot은 `robot/docs/ai-ros-contract-v1.md`의 ROS 2 JSON v1 계약으로만 연결한다.

## 1. 부팅 순서와 장애 정책

```text
network-online.target
  ├─ aiot-ai.service
  │    ├─ ROS Humble setup 적용
  │    ├─ 기존 Python 3.10 AI venv 실행
  │    └─ /ai/status READY 확인 후 /run/aiot/ai-ready.json 생성
  │
  └─ aiot-update.service
       └─ 승인된 stable manifest 확인 후 새 Robot 버전만 활성화

aiot-robot.service
  ├─ Requires/After: aiot-update.service
  └─ Wants/After: aiot-ai.service
```

AI가 죽어도 Robot을 함께 죽이지 않는다. Robot은 `/ai/status`의 2초 heartbeat를 기준으로 판단하고, AI가 없거나 오래됐거나 비정상이면 LIMITED 모드로 동작한다.

## 2. AI 런타임 계약

기존 실행 기준은 다음과 같다.

```text
/home/e103/yolo-pipeline/venv/bin/python -m yolo_pipeline.main
```

`aiot-ai.service` wrapper가 먼저 `/opt/ros/humble/setup.bash`를 source하므로, 별도 system Python ROS bridge는 필요 없다.

AI 프로세스는 다음 계약을 제공해야 한다.

- `/ai/control`: reliable, transient-local, keep-last 1
- `/ai/status`: reliable, volatile, keep-last 5, 즉시 1회 및 2초마다 발행
- `/ai/detections`: reliable, volatile, keep-last 100
- `ROS_LOCALHOST_ONLY=1`
- evidence 저장 위치: `/var/lib/aiot/evidence`
- engine 로드, 카메라 open, warm-up inference 1회가 성공한 뒤에만 READY 발행

`aiot-ai-wait-ready`는 최초의 정상 READY heartbeat를 확인해 `/run/aiot/ai-ready.json`을 원자적으로 만든다. 제한 시간 안에 READY가 없으면 systemd가 AI 시작 실패로 판단하고 제한된 횟수만 재시작한다.

AI 환경변수 예시는 `ai.env.example`에 있다. Backend URL, MQTT 계정, Robot 서비스 토큰은 AI 설정에 넣지 않는다. 외부 전송은 Robot이 담당한다.

## 3. Robot 릴리스 계약

릴리스 태그는 반드시 `iot-vX.Y.Z` 형식이며, `iot/master`에 포함된 커밋을 가리켜야 한다.

CI가 만드는 패키지:

```text
aiot-iot-vX.Y.Z.tar.gz
  ├─ robot/
  ├─ scripts/install.sh
  ├─ scripts/smoke-test.sh
  ├─ VERSION
  ├─ manifest.json
  └─ CHECKSUMS.sha256
```

`iot_publish`는 보호된 수동 job이다. 실행하면 GitLab Generic Package Registry에 불변 패키지를 올리고 EC2의 다음 manifest를 원자적으로 교체한다.

```text
/srv/aiot/releases/jetson/iot/stable/manifest.json
```

공개 조회 주소:

```text
https://i15e103.p.ssafy.io/jetson/releases/iot/stable/manifest.json
```

manifest에는 Robot commit, 필요한 AI 계약 버전, JetPack, CPU 아키텍처, 패키지 크기와 SHA-256만 기록한다. 비밀값이나 AI 모델은 기록하지 않는다.

## 4. 태그 생성 방법

현재 GitLab 보호 태그 규칙은 `iot-v*`, 생성 가능 역할은 Developer와 Maintainer다.

```bash
git fetch origin --tags
git switch iot/master
git pull --ff-only origin iot/master

# 기존 태그가 iot-v0.1.1이면 다음은 iot-v0.1.2
git tag -a iot-v0.1.2 -m "iot v0.1.2"
git push origin iot-v0.1.2
```

자주 발생하는 실수:

| 증상 | 원인·해결 |
| --- | --- |
| 로컬에는 태그가 있는데 GitLab에 없음 | `git push origin iot-vX.Y.Z`를 실행하지 않음 |
| 태그 파이프라인이 생기지 않음 | `jetson-v*`, `v1.0.0` 등 잘못된 이름 사용 |
| 태그가 거부됨 | GitLab 역할이 Developer 미만이거나 동일 태그가 이미 존재 |
| 패키지는 만들어졌지만 stable이 그대로임 | 파이프라인의 `iot_publish` 수동 실행을 하지 않음 |
| 수정한 코드를 포함하지 않음 | 최신 `iot/master`를 pull하지 않고 다른 commit에 태그 생성 |

이미 게시된 태그를 삭제·재사용하지 않는다. 문제가 있으면 patch 버전을 올린 새 태그를 만든다.

## 5. GitLab 게시 절차

1. GitLab `Build > Pipelines > Tags`로 이동한다.
2. 새 태그 파이프라인의 `iot_package`가 성공했는지 확인한다.
3. deploy stage의 `iot_publish`에서 `Run`을 누른다.
4. 파이프라인이 Passed인지 확인한다.
5. stable manifest의 `release`가 새 태그인지 확인한다.

```bash
curl -fsS \
  https://i15e103.p.ssafy.io/jetson/releases/iot/stable/manifest.json
```

태그 생성은 릴리스 후보를 고정하는 작업이고, `iot_publish`는 실제 Jetson stable 채널을 바꾸는 승인 작업이다. 두 단계를 분리해 실수로 모든 Jetson이 미검증 패키지를 받는 것을 막는다.

## 6. Jetson 최초 설치

검토한 `infra/jetson` 파일을 인증된 방법으로 Jetson에 전달하고, 먼저 서비스를 활성화하지 않은 상태로 설치한다.

```bash
sudo bash infra/jetson/install.sh

sudo install -m 0600 -o root -g root \
  infra/jetson/ai.env.example /opt/aiot/secrets/ai.env

sudo install -m 0600 -o root -g root \
  infra/jetson/package-read.env.example \
  /opt/aiot/secrets/package-read.env
```

`package-read.env`에는 `read_package_registry` 권한만 가진 GitLab Deploy Token을 넣는다. `ai.env`에서는 AI 경로와 선택적인 카메라·engine 검사 설정을 확인한다. 설치 스크립트는 기존 secret이나 AI 런타임 파일을 덮어쓰지 않는다.

## 7. 안전한 수동 검증

### 7.1 Robot OTA만 검증

구동부가 멈췄는지 확인하고 Robot 서비스를 중지한 뒤 updater를 실행한다.

```bash
sudo systemctl stop aiot-robot.service
sudo /opt/aiot/bin/aiot-update

cat /opt/aiot/iot/state/VERSION
readlink -f /opt/aiot/iot/current
sudo journalctl -u aiot-update.service -n 100 --no-pager
```

같은 명령을 한 번 더 실행했을 때 다음 메시지가 나오면 버전 비교까지 정상이다.

```text
phase=compare result=already-current
```

### 7.2 AI와 Robot 서비스 검증

```bash
sudo systemctl start aiot-ai.service
sudo systemctl status aiot-ai.service --no-pager
sudo journalctl -u aiot-ai.service -n 100 --no-pager
sudo test -s /run/aiot/ai-ready.json

sudo systemctl start aiot-robot.service
sudo systemctl status aiot-robot.service --no-pager
sudo journalctl -u aiot-robot.service -n 100 --no-pager
```

정상 모드, AI 장애 LIMITED 모드, 종료, 재부팅을 모두 확인한 뒤 자동 시작 범위를 정한다.

```bash
# 부팅 시 버전 확인만 먼저 사용
sudo systemctl enable aiot-update.service

# AI와 Robot까지 검증을 마친 뒤에만 추가
sudo systemctl enable aiot-ai.service aiot-robot.service
```

`sudo bash infra/jetson/install.sh --enable`은 세 서비스를 한꺼번에 enable하므로 모든 환경 검토가 끝난 뒤 사용한다.

## 8. updater 검증과 롤백

부팅 또는 수동 실행 시 updater는 다음 순서로 동작한다.

1. 공개 stable manifest 다운로드
2. 스키마, component, AI 계약, JetPack, CPU 아키텍처 확인
3. artifact host와 경로 allowlist 확인
4. read-only Deploy Token으로 비공개 패키지 다운로드
5. 패키지 크기와 SHA-256 확인
6. 위험한 압축 경로, AI 모델 포함 여부, 내부 체크섬 확인
7. 의존성 설치 및 구동 명령 없는 pre-activation smoke 실행
8. `/opt/aiot/iot/current`를 새 릴리스로 원자적 교체
9. post-activation smoke와 5초 stationary probe 실행
10. 실패하면 이전 symlink 복원

네트워크, 호환성, 다운로드 또는 검증이 실패하면 현재 정상 릴리스를 유지한다. 최초 설치인데 정상 릴리스가 하나도 없으면 Robot을 실행 가능한 상태라고 거짓 보고하지 않고 정지 상태를 유지한다.

## 9. 2026-08-02 실기 검증 결과

- `iot-v0.1.0`: 다운로드와 인증은 성공했지만 과거 패키징의 최상위 `.` 항목을 안전 검사기가 거부함
- 수정: 패키지에 `robot`, `scripts`, `VERSION`, `manifest.json`, `CHECKSUMS.sha256`만 명시적으로 포함
- `iot-v0.1.1`: 다운로드, SHA-256, 압축 안전성, AI 계약, Python 3.10.12, ROS Humble, pre/post smoke와 원자적 활성화 통과
- 재실행: `already-current` 통과
- 활성 버전: `/opt/aiot/iot/releases/iot-v0.1.1`
- `aiot-update.service`: 부팅 자동 확인 enabled
- `aiot-ai.service`, `aiot-robot.service`: 환경 검토 전이므로 disabled 유지

`iot-v0.1.0`을 재사용하지 말고 이후 버전은 반드시 `iot-v0.1.1`보다 높게 만든다.

## 10. 애플리케이션 파트에 남은 연결

Infra는 AI 또는 Robot 기능을 다시 구현하지 않는다.

- AI는 `yolo_pipeline.main`에서 ROS 계약을 발행해야 한다.
- 주행·미션 담당자는 `START_PATROL` 전에 `AiRosBridge.gate.decision()`을 호출해야 한다.
- 순찰 시작·정지 시 `set_detection_enabled()`를 연결해야 한다.
- 미션 adapter는 detection outbox에 Robot pose를 결합하고 Backend REST DTO로 전달해야 한다.

이 연결은 systemd와 OTA 계약을 바꾸지 않고 애플리케이션 내부에서 완성한다.
