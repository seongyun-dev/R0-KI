# 로봇 실시간 영상 중계

현재 시연 로봇 `robotId=16`의 영상을 다음 경로로 중계한다.

```text
Jetson 127.0.0.1:8090
  -> SSH 역방향 터널
EC2 127.0.0.1:19001
  -> Nginx 내부 영상 세션 검증
HTTPS /live/robots/17/stream.mjpg
```

브라우저는 로그인 JWT로 `POST /api/robots/17/stream-sessions`를 호출한다. 백엔드는 사용자가
해당 로봇을 조회할 권한이 있는지 확인하고 60초짜리 일회용 토큰을 발급한다. 브라우저는 이 토큰을
`X-Stream-Token` 헤더로 전송하고, Nginx는 내부 검증 API에서 토큰을 한 번 소비한 뒤 MJPEG 연결을 연다.

내부 8090/19001 포트는 외부에 공개하지 않는다. 내부 검증 API도 Nginx의 공개 `/api/` 경로에서는
404로 차단한다. 영상 경로는 토큰이 로그에 남지 않도록 접근 로그를 끈다.

점검:

```bash
ss -lnt | grep 19001
curl -fsS http://127.0.0.1:19001/health
nginx -t
```

다른 로봇을 추가할 때는 로봇별 터널 포트와 Nginx 영상 경로를 함께 추가해야 한다.
