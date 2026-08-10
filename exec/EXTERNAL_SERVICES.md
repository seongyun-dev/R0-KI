# 외부 서비스 사용 가이드

확인 기준: 2026-08-10

운영 비밀번호와 API Key는 Git에 저장하지 않는다. 이 문서에는 발급 방법, 필요한 권한, 환경변수와 등록 위치만 기록한다.

## 1. 사용 중인 외부 서비스

| 서비스 | 용도 | 필요한 정보 | 등록 위치 |
| --- | --- | --- | --- |
| SSAFY GitLab | 소스, CI/CD, IoT 패키지 저장 | 프로젝트 권한, Runner, Deploy Token | GitLab 프로젝트와 Jetson |
| Mattermost | CI/CD 결과 알림 | Incoming Webhook URL | GitLab 변수 `MM_WEBHOOK_URL` |
| SSAFY GMS | 순찰 요약과 분석 생성 | GMS API Key | Backend `GMS_KEY` |
| Gmail SMTP | 회원가입 이메일 인증 | Gmail 계정, 앱 비밀번호 | Backend `MAIL_USERNAME`, `MAIL_PASSWORD` |
| Solapi | 긴급 알림 문자 발송 | API Key, Secret, 등록 발신번호 | Backend `SOLAPI_*` |
| Let's Encrypt | HTTPS와 MQTT TLS 인증서 | 도메인 DNS 인증 권한 | EC2 `/etc/letsencrypt` |
| SSAFY GPU 서버 | AI 학습과 TensorRT 변환 | 서버 계정, Device 3 Runner | GitLab Runner `ai-gpu-device3` |
| AWS EC2 | 웹, API, DB, MQTT, GitLab Runner 운영 | PEM 키 | 운영 담당자 PC |

소셜 로그인, S3, RDS, Firebase, 외부 지도 API는 사용하지 않는다. MySQL과 Mosquitto는 EC2의 Docker 컨테이너로 직접 운영한다.

## 2. GitLab과 Package Registry

- 프로젝트: `https://lab.ssafy.com/s15-webmobile3-sub1/S15P11E103`
- 일반 개발자는 Developer, 브랜치·Runner·CI 변수 관리자는 Maintainer 권한이 필요하다.
- EC2 Runner는 `aiot-ec2`, GPU Runner는 `ai-gpu-device3` 태그를 사용한다.
- Frontend와 Backend 이미지는 EC2의 로컬 Docker에 저장한다.
- IoT 패키지만 GitLab Generic Package Registry에 저장한다.

Jetson용 Deploy Token은 프로젝트의 **Settings → Repository → Deploy tokens**에서 만든다.

```text
권한: read_package_registry
보관: /opt/aiot/secrets/package-read.env
변수: PACKAGE_REGISTRY_USER, PACKAGE_REGISTRY_TOKEN
```

쓰기 권한이나 개인 Access Token을 Jetson에 넣지 않는다. 토큰 만료일을 설정했다면 시연 전에 갱신한다.

## 3. Mattermost

- 채널: `https://meeting.ssafy.com/s15p10e1/channels/e103_v2`
- 채널의 **통합 → Incoming Webhook**에서 Webhook을 생성한다.
- GitLab **Settings → CI/CD → Variables**에 다음과 같이 등록한다.

```text
Key: MM_WEBHOOK_URL
Value: 발급받은 Webhook URL
Protected: 사용
Masked: 사용
```

Webhook URL은 `.gitlab-ci.yml`이나 `.env`에 작성하지 않는다. 알림 형식은 `infra/scripts/notify-mattermost.sh`에서 관리한다.

## 4. SSAFY GMS

SSAFY GMS에서 API Key를 발급받아 사용한다. 운영 설정은 다음과 같다.

| 변수 | 값 또는 설명 |
| --- | --- |
| `GMS_BASE_URL` | `https://gms.ssafy.io/gmsapi/api.openai.com/v1` |
| `GMS_KEY` | 발급받은 API Key |
| `GMS_MODEL` | 현재 운영 `gpt-5-mini` |
| `GMS_CHAT_COMPLETIONS_PATH` | `/chat/completions` |
| `GMS_TIMEOUT_SECONDS` | `120` |

Key는 `/srv/aiot/secrets/backend.env`에만 저장한다. Key가 없으면 AI 요약·분석 기능만 실패하며 Robot 제어와 기본 순찰 데이터 저장에는 영향을 주지 않는다.

## 5. Gmail SMTP

1. 발송용 Google 계정에 2단계 인증을 설정한다.
2. Google 계정에서 앱 비밀번호를 발급한다.
3. EC2의 `/srv/aiot/secrets/backend.env`에 등록한다.

```env
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=<발송 계정>
MAIL_PASSWORD=<앱 비밀번호>
MAIL_FROM=<발신 주소>
```

SMTP는 STARTTLS와 인증을 사용한다. 운영에서는 `APP_EMAIL_VERIFICATION_ENABLED=true`를 유지한다. 개인 계정 비밀번호를 `MAIL_PASSWORD`로 사용하지 않는다.

## 6. Solapi

1. Solapi 계정을 만든다.
2. 콘솔에서 API Key와 API Secret을 발급한다.
3. 문자 발신번호를 등록하고 승인을 완료한다.
4. 다음 값을 `/srv/aiot/secrets/backend.env`에 등록한다.

```env
SOLAPI_API_KEY=<API Key>
SOLAPI_API_SECRET=<API Secret>
SOLAPI_SENDER_NUMBER=<승인된 발신번호>
```

등록되지 않은 발신번호를 사용하면 문자 발송이 거절된다. 시연 전 잔액과 일일 발송 제한도 확인한다.

## 7. 도메인과 TLS

- 서비스 도메인: `i15e103.p.ssafy.io`
- Nginx 인증서: `/etc/letsencrypt/live/p.ssafy.io/`
- MQTT 외부 접속: `i15e103.p.ssafy.io:8883`, TLS 사용

현재 인증서는 wildcard 도메인의 수동 DNS 인증 방식이다. 자동 갱신으로 간주하지 말고 만료 전에 DNS 인증으로 갱신한다.

```bash
sudo /srv/aiot/deploy/sync-certificates.sh
sudo /srv/aiot/deploy/health-check.sh infrastructure
```

인증서 개인키는 Git에 복사하지 않는다.

## 8. 서버 접근

### EC2

```bash
ssh -i I15E103T.pem ubuntu@i15e103.p.ssafy.io
```

PEM 키는 운영 담당자에게 별도 전달한다. AWS Access Key는 사용하지 않는다.

### GPU 서버

```text
주소: http://70.12.130.103
계정: i15e103
GPU: Device 3
Runner tag: ai-gpu-device3
```

GPU 서버 계정 비밀번호와 Runner 인증 토큰은 문서에 기록하지 않는다.

## 9. 운영 비밀값 점검표

| 위치 | 확인할 값 |
| --- | --- |
| GitLab CI/CD Variables | `MM_WEBHOOK_URL` |
| `/srv/aiot/secrets/backend.env` | GMS, 메일, Solapi, DB, MQTT, JWT |
| `/srv/aiot/secrets/runtime.env` | MySQL, MQTT 초기 비밀값 |
| `/opt/aiot/secrets/package-read.env` | Jetson Package Registry 읽기 토큰 |
| `/opt/aiot/secrets/robot.env` | Robot Key, MQTT TLS, Backend token |

운영 인수인계 때는 문서가 아니라 비밀관리 채널을 통해 값을 전달한다.
