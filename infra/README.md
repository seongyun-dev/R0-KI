# AIoT 인프라 안내

이 디렉터리는 단일 AWS EC2 운영 환경, GitLab Runner 기반 CI/CD, Jetson Pull OTA 설정을 관리한다.

처음 보는 사람은 다음 순서로 문서를 읽으면 된다.

1. 이 문서: 전체 구조와 일상적인 작업 흐름
2. [CICD_V2_OPERATIONS.md](CICD_V2_OPERATIONS.md): 파트별 브랜치·배포·통합 규칙
3. [OPERATIONS.md](OPERATIONS.md): EC2 점검, 백업, 장애 대응 명령
4. [jetson/README.md](jetson/README.md): Jetson AI 서비스와 Robot Pull OTA
5. [CONTRACTS.md](CONTRACTS.md): 각 파트가 CI/CD에 제공해야 하는 파일과 실행 계약

`HANDOFF.md`와 `CICD_MIGRATION_HANDOFF.md`는 구축 과정과 과거 결정을 보존하는 참고 자료다. 현재 운영 방법은 위 문서들을 우선한다.

## 현재 구성

```text
사용자
  -> HTTPS 443
  -> EC2 호스트 Nginx
       -> /       : Frontend 컨테이너(127.0.0.1:3000)
       -> /api/   : Backend 컨테이너(127.0.0.1:8080)
       -> /docs   : Swagger UI

Backend
  -> MySQL(aiot-mysql:3306)
  -> Mosquitto(aiot-mosquitto:1883, Docker 내부망)

Jetson
  -> MQTT TLS 8883
  -> 부팅 시 승인된 Robot 릴리스 확인 후 필요한 경우에만 Pull OTA
```

- MySQL과 Mosquitto는 `compose.infrastructure.yaml`로 관리한다.
- Frontend와 Backend는 `compose.application.yaml`로 관리한다.
- Nginx가 HTTPS 종료와 경로별 프록시를 담당한다.
- Jetson의 AI와 Robot은 서로 다른 생명주기로 관리한다.

## 브랜치와 배포

```text
작업 브랜치 -> 파트/dev -> 파트/master -> develop -> 최상위 master
```

| 위치 | 의미 | 자동 동작 |
| --- | --- | --- |
| `front/dev`, `back/dev`, `ai/dev`, `iot/dev` | 평소 개발 통합 | 해당 파트 CI만 실행 |
| `front/master` | 배포 가능한 Front 버전 | 후보 통합검사 후 Front만 EC2 배포 |
| `back/master` | 배포 가능한 Back 버전 | 후보 통합검사 후 Back만 EC2 배포 |
| `ai/master` | 승인 가능한 AI 코드·모델 기준 | GPU 작업은 별도 수동 승인 |
| `iot/master` | 설치 가능한 Robot 코드 기준 | merge만으로 Jetson 배포하지 않음 |
| `develop` | 배포 성공한 파트 버전 조합 기록 | EC2 재배포 없음 |
| 최상위 `master` | 최종 마일스톤 | 수동 승인 |

파트 작업자는 보통 작업 브랜치를 자기 파트 `dev`로 MR하고, 릴리스할 때만 파트 `master`로 MR한다. Infra 담당자는 파트 master 배포 성공 버전을 확인한 뒤 `develop`에 통합한다.

## Jetson Pull OTA 한눈에 보기

Robot은 `iot/master` merge만으로 배포되지 않는다. 승인할 버전에 `iot-vX.Y.Z` 태그를 생성하고, GitLab에서 `iot_publish`를 수동 실행해야 stable manifest가 바뀐다.

```text
iot/master
  -> iot-vX.Y.Z 태그
  -> iot_package 자동 실행
  -> iot_publish 수동 승인
  -> GitLab Package Registry에 불변 tar.gz 게시
  -> EC2의 stable manifest 교체
  -> Jetson 부팅 시 manifest 확인
  -> 새 버전일 때만 다운로드·검증·활성화
```

태그는 로컬에서 만드는 것과 원격 GitLab에 올리는 것이 별개다.

```bash
git fetch origin
git switch iot/master
git pull --ff-only origin iot/master
git tag -a iot-v0.1.2 -m "iot v0.1.2"
git push origin iot-v0.1.2
```

현재 보호 태그 규칙은 `iot-v*`이며 Developer와 Maintainer가 생성할 수 있다. 태그 이름이 `jetson-v*`이거나 `git push origin <태그>`를 생략하면 OTA 파이프라인이 시작되지 않는다.

2026-08-02 실기 검증에서는 `iot-v0.1.1`의 다운로드, SHA-256, 압축 경로, AI 계약, Python/ROS, 무구동 smoke, 원자적 활성화와 재실행 시 `already-current`까지 통과했다.

## 비밀값

실제 비밀값은 서버의 `/srv/aiot/secrets`와 Jetson의 `/opt/aiot/secrets`에만 둔다.

- `.env`, 비밀번호, Runner 토큰, Deploy Token, 인증서 private key를 Git에 커밋하지 않는다.
- Mattermost Webhook은 GitLab의 protected·masked 변수 `MM_WEBHOOK_URL`로만 관리한다.
- 로그나 문서에 비밀값 전체를 출력하지 않는다.

## 배포 알림

`front/master`, `back/master` 배포와 Jetson 릴리스 게시 결과는 Mattermost 카드로 알린다.

- 초록: 배포와 헬스체크 성공
- 노랑: 후보 통합검사 실패, 운영 변경 없음
- 주황: 배포 실패 후 이전 버전 자동 복구 성공
- 빨강: 배포와 자동 복구 모두 실패하여 즉시 확인 필요
- 파랑: Jetson IoT 릴리스 게시 완료

Mattermost 장애는 실제 배포 성공·실패 판정을 바꾸지 않는다.

## EC2 최초 설치 순서

1. 기존 Nginx와 Mosquitto 설정을 백업한다.
2. `bootstrap-server.sh`를 root로 실행한다.
3. `initialize-secrets.sh`를 root로 실행한다.
4. `sync-certificates.sh`를 실행한다.
5. `deploy-infrastructure.sh`를 실행한다.
6. MySQL·MQTT를 검증한 뒤 Nginx 애플리케이션 사이트를 활성화한다.

기존 Gerrit(8988/29418)과 Apache(8989)는 이 프로젝트 범위 밖이므로 변경하지 않는다. Docker publish 포트는 UFW만으로 차단됐다고 판단하지 말고 AWS Security Group도 함께 확인한다.
