# AI 실시간 MJPEG 운영

## 구성

```text
카메라 2대 → 기존 AI 추론/주석 화면 병합 → Jetson 127.0.0.1:8090
          → SSH 역방향 터널 → EC2 127.0.0.1:19001
          → Nginx HTTPS/백엔드 인증 → 프론트 대시보드
```

- 영상은 메모리에 최신 JPEG 한 장만 보관하며 SD 카드에 계속 쓰지 않는다.
- Jetson의 MJPEG 포트와 EC2의 터널 포트는 모두 loopback에만 바인딩한다.
- 브라우저는 기존 로그인으로 짧은 영상 세션을 발급받고, Nginx 내부 검증을
  통과한 경우에만 영상을 수신한다.
- 서비스 시작 시 모델을 한 번 준비해 `READY` 상태를 유지하지만, 실제 반복
  추론과 MJPEG 프레임 갱신은 순찰 `ENABLE`부터 `DISABLE`까지만 수행한다.
- 현재 시연 로봇은 백엔드 `robotId=16`이고, Nginx 경로는
  `/live/robots/16/stream.mjpg`이다.

## Jetson 설정

`/opt/aiot/secrets/ai.env`:

```dotenv
AIOT_AI_MJPEG_ENABLED=true
AIOT_AI_MJPEG_BIND=127.0.0.1
AIOT_AI_MJPEG_PORT=8090
AIOT_AI_MJPEG_QUALITY=70
AIOT_AI_MJPEG_MAX_FPS=5
```

`/opt/aiot/secrets/stream.env`는 `infra/jetson/stream.env.example`을 기준으로
작성한다. 전용 SSH 개인키와 `known_hosts`는 저장소나 OTA 패키지에 포함하지
않고 Jetson의 `/opt/aiot/secrets/`에만 둔다.

## 무구동 점검

다음 명령은 ESP32 시리얼과 모터를 사용하지 않는다.

```bash
systemctl is-active aiot-ai.service aiot-mjpeg-tunnel.service
curl -fsS http://127.0.0.1:8090/health
```

EC2에서는 터널이 열려 있을 때만 아래 주소가 응답한다.

```bash
curl -fsS http://127.0.0.1:19001/health
```

대기 상태에서는 프론트가 영상 연결을 열지 않는다. 순찰이 시작되면 연결하고,
순찰 종료 또는 서비스 중단 시 마지막 프레임 대신 영상 대기 상태로 돌아간다.
