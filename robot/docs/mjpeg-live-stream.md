# AI 실시간 MJPEG 운영

## 구성

```text
카메라 2대 → 기존 AI 추론/주석 화면 병합 → Jetson 127.0.0.1:8090
          → SSH 역방향 터널 → EC2 127.0.0.1:19001
          → Nginx HTTPS/백엔드 인증 → 프론트 대시보드
```

- 영상은 메모리에 최신 JPEG 한 장만 보관하며 SD 카드에 계속 쓰지 않는다.
- Jetson의 MJPEG 포트와 EC2의 터널 포트는 모두 loopback에만 바인딩한다.
- 브라우저 요청은 기존 로그인 Bearer 토큰으로 로봇 소속 검증을 통과해야 한다.
- 현재 시연 로봇은 백엔드 `robotId=16`이고, Nginx 경로는
  `/live/robots/16/stream.mjpg`이다.

## Jetson 설정

`/opt/aiot/secrets/ai.env`:

```dotenv
AIOT_AI_MJPEG_ENABLED=true
AIOT_AI_MJPEG_BIND=127.0.0.1
AIOT_AI_MJPEG_PORT=8090
AIOT_AI_MJPEG_QUALITY=70
AIOT_AI_MJPEG_MAX_FPS=8
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

서비스가 중단되면 프론트는 마지막 프레임 대신 영상 대기 상태를 표시하고
2초 간격으로 재연결한다.
