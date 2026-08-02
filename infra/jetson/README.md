# Jetson Robot/AI systemd and Pull OTA

Jetson의 두 application lifecycle은 분리한다.

```text
/home/e103/yolo-pipeline          기존 AI 모델·engine·venv (OTA가 수정하지 않음)
/opt/aiot/iot/releases/iot-v*    GitLab robot/ 릴리스
/opt/aiot/iot/current            검증을 통과한 활성 symlink
/var/lib/aiot                    route, evidence, outbox, command cache, ROS log
```

`aiot-ai.service`는 활성 Robot 릴리스의 `aiot_robot.ai_runtime`을 기존 AI venv로
실행한다. 어댑터가 `/home/e103/yolo-pipeline/yolo_pipeline/main.py`를 불러오고
기존 REST sink만 ROS sink로 교체하므로 모델 코드는 수정하지 않는다.
`aiot-robot.service`는 `robot/scripts/run.sh` → `roki-iot/run_integrated.py`를
실행하며 ESP32 시리얼의 유일한 소유자다.

## 부팅과 주기 확인

```text
network-online -> aiot-ai.service -> aiot-robot.service (현재 검증본)
              -> aiot-update.service (새 버전이면 AI -> Robot 재시작 검증)
aiot-update.timer -> boot 2분 후, 이후 5분마다 stable manifest 확인
```

AI 실패 시 Robot은 계속 실행되어 STOP/MQTT/상태 처리를 유지하지만 START는 AI
readiness gate에서 거절된다. updater와 patrol은
`/var/lib/aiot/state/patrol-deploy.lock`을 공유한다. 순찰 중에는 릴리스 활성화를
보류하고, updater가 활성화 중이면 START를 REJECTED 처리한다.

## 최초 설치

검토한 파일을 인증된 경로로 Jetson에 전달한 뒤 실행한다.

```bash
sudo bash infra/jetson/install.sh
```

installer는 계정·디렉터리·udev·systemd만 만들고 기존 secret과 AI 파일을
덮어쓰지 않으며 서비스를 새로 enable하지 않는다. 다음 예시를 mode 0600으로
복사하고 실제 값을 현장에서 입력한다.

```text
/opt/aiot/secrets/package-read.env  <- package-read.env.example
/opt/aiot/secrets/ai.env            <- ai.env.example
/opt/aiot/secrets/robot.env         <- robot/config/robot.env.example
```

검증 후 부팅 자동 시작을 활성화한다.

```bash
sudo bash infra/jetson/install.sh --enable
```

첫 릴리스처럼 아직 `current`가 없으면 AI/Robot의 Condition이 false이므로 updater
완료 뒤 두 서비스를 수동 start한다. 이후 부팅은 current를 즉시 시작하고 updater가
새 릴리스를 발견했을 때만 잠금 아래 재시작한다. 서비스에서 updater를 `After=`로
기다리게 하지 않는 이유는 updater 내부의 동기 재시작과 교착하지 않게 하기 위해서다.

## OTA 보장

protected `iot-vX.Y.Z` tag의 manual `iot_publish`가 Robot-only archive를 GitLab
Generic Package Registry에 올리고 stable manifest를 교체한다. updater는 다음을
검증한다.

1. HTTPS, allowlisted host/path, exact manifest schema
2. JetPack 6.2, aarch64, AI contract version
3. archive size와 SHA-256, 내부 checksum, 안전한 archive path
4. AI model/engine, `.env`, token, local route 미포함
5. dependency install과 actuator-free pre smoke
6. atomic `current` 교체와 post smoke
7. 이전에 active였던 AI → Robot 순서의 재시작

post smoke 또는 서비스 재시작 실패 시 `current`를 이전 release로 되돌리고 이전
서비스를 복구한다. 이미 설치한 버전, network/manifest/checksum 오류, 순찰 중인
경우에는 현재 release를 유지한다.

## 진단

```bash
systemctl status aiot-update.timer aiot-update.service --no-pager
systemctl status aiot-ai.service aiot-robot.service --no-pager
systemctl list-timers aiot-update.timer --no-pager
journalctl -u aiot-update.service -n 100 --no-pager
journalctl -u aiot-ai.service -n 100 --no-pager
journalctl -u aiot-robot.service -n 200 --no-pager
readlink -f /opt/aiot/iot/current
readlink -f /opt/aiot/iot/previous
```

실물 시작·검증 순서와 기대 결과는
`robot/docs/integrated-runtime-operations.md`를 따른다.
