# 로봇 실시간 영상 중계

현재 시연 로봇 `robotId=16`의 영상은 다음 경로로 중계한다.

```text
Jetson 127.0.0.1:8090
  → SSH 역방향 터널
EC2 127.0.0.1:19001
  → Nginx + GET /api/robots/16 인증
HTTPS /live/robots/16/stream.mjpg
```

외부에 8090/19001 포트를 열지 않는다. Nginx는 브라우저가 보낸 기존 Bearer
토큰으로 백엔드 로봇 상세 API를 호출하고, 소속 단지의 로봇으로 확인된 경우에만
MJPEG를 전달한다.

점검:

```bash
ss -lnt | grep 19001
curl -fsS http://127.0.0.1:19001/health
nginx -t
```

로봇 ID나 터널 포트를 바꾸면 `infra/nginx/aiot.conf.template`, Jetson의
`/opt/aiot/secrets/stream.env`, 프론트에서 선택하는 로봇 ID를 함께 맞춘다.
