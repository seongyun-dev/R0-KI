# 파트별 릴리스 CI/CD 전환 기록

> 설계와 전환 과정을 보존하는 문서다. 이미 적용된 현재 운영 절차는
> `CICD_V2_OPERATIONS.md`와 `README.md`를 우선한다.

이 문서는 2026-07-22에 합의한 다음 단계의 인프라·CI/CD 전환 계획을 기록한다.
현재 운영 상태를 설명하는 문서가 아니라, **다음 작업자가 구현해야 하는 목표 구조와 안전한 적용 순서**를 설명한다.

- 프로젝트: `S15P11E103`
- 저장소: `https://lab.ssafy.com/s15-webmobile3-sub1/S15P11E103.git`
- 배포 호스트: `ubuntu@i15e103.p.ssafy.io`
- 작업 기준 브랜치: `infra/dev`
- 비밀 값, 인증서, SSH 키, Runner token은 이 문서와 Git에 기록하지 않는다.

## 1. 최종 결정

최종 목표는 **파트별 독립 CI/CD + 공통 Infra 통합검증·배포 + Release Manifest 기반 버전관리**다.

```text
작업 브랜치
  -> 파트/dev
  -> 파트/master
  -> develop
  -> root master(main)
```

파트별 흐름은 다음과 같다.

```text
front/feature/* -> front/dev -> front/master --┐
back/feature/*  -> back/dev  -> back/master  ---|
ai/feature/*    -> ai/dev    -> ai/master    ---+-> develop -> master
iot/feature/*   -> iot/dev   -> iot/master   ---|
infra/feature/* -> infra/dev -> infra/master --┘
```

브랜치 역할:

| 브랜치 | 역할 | 운영 배포 |
| --- | --- | --- |
| `*/dev` | 평소 파트 개발 통합, 빠른 CI | 없음 |
| `front/master` | 배포 가능한 Frontend 릴리스 | Frontend만 자동 배포 |
| `back/master` | 배포 가능한 Backend 릴리스 | Backend만 자동 배포 |
| `ai/master` | 설치 가능한 AI 릴리스 | 패키지 게시, EC2 런타임 배포 없음 |
| `iot/master` | 설치 가능한 IoT/Robot 릴리스 | 패키지 게시, EC2 런타임 배포 없음 |
| `infra/master` | 공통 CI·Compose·Nginx·MQTT·배포 코드 | 수동 승인 |
| `develop` | 검증된 파트 릴리스를 주기적으로 모으는 통합 소스 | 운영 자동 배포 없음 |
| root `master` | 발표·최종 마일스톤 | 수동 승인 또는 기록 전용 |

중요한 원칙:

```text
개별 CI 통과 != 배포 가능

개별 CI 통과
+ 현재 안정 버전과 계약/통합 검증
= 파트 master 머지 및 배포 가능
```

`develop`은 파트 배포 전 안전 게이트가 아니다. 파트 master가 먼저 배포되므로, 배포 안전은
반드시 파트 master MR의 후보 통합 테스트가 담당한다. `develop`은 검증된 전체 소스를
재현하고 최종 `master`를 만들기 위한 마일스톤 브랜치다.

## 2. 현재 구현과 목표의 차이

현재 저장소와 서버에는 다음 기반이 이미 존재한다.

- EC2 Project Runner `aiot-ec2`, Shell executor, 단일 동시 실행
- Host Nginx, Docker Compose application/infrastructure 분리
- `aiot-frontend`, `aiot-backend`, `aiot-mysql`, `aiot-mosquitto`
- 변경 경로에 따라 Frontend/Backend만 선택하는 `infra/scripts/deploy.sh`
- Frontend/Backend image와 commit을 별도 저장하는 `/srv/aiot/deploy/current.env`
- 배포 직전 상태 한 세트를 복구하는 `infra/scripts/rollback.sh`
- Jetson Pull OTA updater, package, checksum, smoke, rollback 골격

현재 CI/CD의 주요 차이와 한계:

| 현재 | 목표 |
| --- | --- |
| `develop` push가 EC2 앱 자동 배포 | 파트 master가 해당 파트만 배포 |
| root `master`가 수동 전체 배포 | root `master`는 최종 릴리스 |
| `front/master`, `back/master`, `ai/master`, `iot/master` 미사용 | 파트별 릴리스 기준으로 사용 |
| image tag가 통합 commit 중심 | 파트별 불변 commit/image tag |
| `previous.env` 한 세트만 보존 | 파트별·릴리스별 Manifest 이력 |
| `infra/smoke` 더미 서비스 검사 | 실제 후보 앱과 안정 상대 버전 통합검사 |
| AI+IoT `jetson-v*` 통합 bundle | 향후 파트별 artifact + 통합 stable manifest |

2026-07-22 확인 당시 원격 `front/master`, `back/master`, `ai/master`, `iot/master`, root
`master`는 모두 초기 commit `3218c27`을 가리켰다. 실제 전환 전에 다시 fetch하고 확인한다.
보호 브랜치에 force push하지 말고 MR로 초기 동기화한다.

## 3. 목표 런타임 구조

새 EC2, Jenkins, RDS, AWS IoT Core를 추가하지 않는다.

```text
Internet
  -> HTTPS 443
       -> Host Nginx
            -> /       -> 127.0.0.1:3000 -> aiot-frontend
            -> /api/*  -> 127.0.0.1:8080 -> aiot-backend
            -> /jetson/releases/stable/manifest.json

Docker network: aiot-network
  - aiot-frontend
  - aiot-backend
  - aiot-mysql:3306      # host에 publish하지 않음
  - aiot-mosquitto:1883  # backend 내부 통신

Jetson
  -> MQTT TLS 8883
  -> HTTPS API
  -> 부팅 시 stable manifest 확인 및 Pull OTA
```

파트 배포는 동일한 Compose project 안에서 서비스 이름을 지정해 수행한다.

```bash
docker compose ... up -d frontend
docker compose ... up -d backend
```

Frontend 배포가 Backend, MySQL, Mosquitto를 재시작하면 안 된다. Backend 배포가
Frontend를 재시작하면 안 된다.

## 4. 작업자 흐름

### 4.1 평소 개발

```text
파트/dev에서 feature 브랜치 생성
-> 구현 및 push
-> feature -> 파트/dev MR
-> review + 파트 CI
-> merge
```

개발자는 `develop`, 파트 master, root `master`에 직접 push하지 않는다.

### 4.2 파트 배포

배포할 기능이 모이면 파트 담당자가 `파트/dev -> 파트/master` MR을 만든다.

```text
파트 CI
-> 후보 불변 이미지 생성
-> 후보 파트 + 현재 운영 상대 파트 + Infra 통합검사
-> 성공 시 merge 가능
-> master merge pipeline에서 동일 후보 재검증
-> 해당 파트만 배포
-> readiness/health 확인
-> 성공 시 Release Manifest 갱신
-> 실패 시 해당 파트만 이전 이미지로 복구
```

배포 성공 전에는 의미 버전 tag를 stable로 취급하지 않는다. 실제 운영 버전은 Git branch
HEAD가 아니라 Release Manifest와 GitLab Environment 상태를 기준으로 판단한다.

### 4.3 develop 통합

매 배포마다 develop을 갱신하지 않는다. 하루 1회, 주요 기능 완료, 발표 전과 같은
마일스톤에 Infra 담당자가 수행한다.

```text
배포 성공한 파트 release 선택
-> release/integration-vX.Y.Z 생성
-> 선택한 파트 master commit 통합
-> 전체 계약·통합 테스트
-> Release Manifest와 source 조합 확인
-> develop MR
-> integration-vX.Y.Z 기록
```

파트 master의 단순 최신 HEAD가 아니라 **마지막 배포 성공 commit/tag**를 선택한다.
AI 또는 IoT가 준비되지 않았다면 해당 파트는 이전 안정 버전 또는 `pending` 상태를 유지한다.

## 5. Pipeline 책임 분리

### 5.1 dev CI

| 파트 | 필수 검사 |
| --- | --- |
| Frontend | `npm ci`, lint, TypeScript/build |
| Backend | Java 21, Gradle test, build |
| AI | 코드가 있을 때 Python compile/lint, dependency, model metadata |
| IoT | 코드가 있을 때 Python/ROS2 package, MQTT schema |
| Infra | shell syntax, contract, Compose render, manifest schema |

dev CI는 빠르게 유지하고 운영 배포를 수행하지 않는다.

### 5.2 master MR 후보 통합검사

Frontend 후보:

```text
새 Frontend image
+ Release Manifest의 현재 안정 Backend image
+ MySQL
+ Mosquitto
+ 실제 Nginx 설정
```

Backend 후보:

```text
새 Backend image
+ Release Manifest의 현재 안정 Frontend image
+ MySQL
+ Mosquitto
+ 실제 Nginx 설정
```

통합 테스트에서 검증한 image와 운영에 배포할 image가 달라지면 안 된다. 우선 동일 EC2
Shell Runner의 로컬 Docker image를 사용하고, Container Registry가 활성화되어 있다면
같은 불변 tag를 push하는 방식으로 확장한다.

### 5.3 master merge CD

| 트리거 | 자동 동작 |
| --- | --- |
| `front/master` push | Frontend 후보 확인, Frontend만 배포, 검증, Manifest 갱신 |
| `back/master` push | Backend 후보 확인, Backend만 배포, 검증, Manifest 갱신 |
| `ai/master` push | AI artifact/version/checksum 생성 및 Package Registry 게시 |
| `iot/master` push | IoT artifact/version/checksum 생성 및 Package Registry 게시 |
| `infra/master` push | 기본은 수동 승인, 공통 설정 배포와 전체 검증 |

AI/IoT master merge는 Jetson stable channel을 즉시 갱신하지 않는다.

## 6. Release Manifest

운영 상태의 source of truth는 다음 파일이다.

```text
/srv/aiot/deploy/release-manifest.json
/srv/aiot/deploy/releases/<release-id>.json
```

구현 예시:

```json
{
  "schemaVersion": 1,
  "releaseId": "release-20260722-01",
  "releasedAt": "2026-07-22T09:00:00Z",
  "integrationStatus": "passed",
  "deployedComponents": ["frontend"],
  "frontend": {
    "enabled": true,
    "image": "aiot-frontend:front-a82f910",
    "commit": "a82f910",
    "branch": "front/master"
  },
  "backend": {
    "enabled": true,
    "image": "aiot-backend:back-b9412fc",
    "commit": "b9412fc",
    "branch": "back/master",
    "databaseSchema": "3"
  },
  "ai": {"status": "pending", "version": null, "artifact": null, "checksum": null},
  "iot": {"status": "pending", "version": null, "artifact": null, "checksum": null},
  "infra": {"commit": "c913a10", "pipelineId": "100", "jobId": "200"},
  "mqttSchema": 1
}
```

요구사항:

- image에 `latest`를 사용하지 않는다.
- 임시 파일에 쓰고 검증 후 atomic rename한다.
- 배포 성공 후에만 현재 Manifest를 바꾼다.
- 각 성공 release의 Manifest를 별도 보존한다.
- 비밀 값이나 Deploy Token을 기록하지 않는다.
- 실제 Git tag보다 Manifest의 image digest/commit을 우선한다.

## 7. 통합 테스트 범위와 점진적 활성화

현재 모든 예정 API를 blocking test로 만들면 Pipeline이 계속 실패한다. 테스트를 다음 두
상태로 관리한다.

```text
required: 현재 구현 완료, 실패 시 master merge/deploy 차단
planned: 아직 개발 중, 결과만 표시하고 차단하지 않음
```

초기 `required` 범위:

1. 실제 Frontend/Backend Docker image 기동
2. MySQL 연결 및 Flyway migration
3. Nginx `/`와 `/api/` proxy
4. Frontend를 `VITE_USE_MOCKS=false`로 build
5. 회원가입 또는 준비된 fixture, 로그인, JWT 발급
6. JWT를 사용한 `/api/robots` 기본 요청
7. Mosquitto 인증 publish/subscribe round trip
8. 컨테이너 readiness와 실패 로그 수집
9. 테스트 후 임시 Compose project와 volume 정리

기능 완성 순서에 따라 `required`에 추가한다.

```text
Auth/Robot
-> Patrol/Event
-> Map/SSE
-> MQTT event -> Backend -> DB -> API
-> AI/IoT package와 Jetson OTA
```

현재 확인된 차이:

- Frontend는 기본적으로 Mock 사용이 활성화될 수 있으므로 통합 build에서 반드시 끈다.
- Frontend가 참조하는 Patrol/Event/Map/Statistics/SSE API 중 일부는 Backend에 아직 없다.
- Backend에는 Actuator와 MQTT client dependency가 아직 없다.
- Backend unit test는 H2 MySQL compatibility mode를 사용하므로 실제 MySQL 검사가 별도로 필요하다.
- `ai/dev`는 더미 파일 중심이고 `iot/dev`의 Robot 코드는 아직 준비되지 않았다.
- 기존 `infra/smoke`는 실제 애플리케이션 호환성 검사가 아닌 격리 fixture다.

통합 테스트는 공개 계약에만 결합한다.

- REST: OpenAPI, 요청/응답 schema
- MQTT: topic, QoS, JSON schema, schema version
- Jetson: package manifest, JetPack/CUDA/TensorRT/architecture 조건

Frontend 테스트가 Java class나 DB table을 직접 알게 만들지 않는다. 실제 Jetson과 모터를
일반 서버 CI의 필수 조건으로 연결하지 않는다.

## 8. 배포·롤백 정책

자동 실패 복구:

```text
새 파트 container 실행
-> readiness 실패
-> 해당 파트의 이전 image 복원
-> 이전 Manifest 유지
-> Pipeline 실패 표시
```

수동 선택 롤백 목표:

```bash
rollback.sh frontend <image-or-release>
rollback.sh backend <image-or-release>
rollback.sh release <release-id>
```

- 독립적인 Frontend 오류는 Frontend만 되돌린다.
- 독립적인 Backend 오류는 Backend만 되돌린다.
- API 계약이 함께 바뀌었다면 검증된 Frontend+Backend Manifest 조합으로 되돌린다.
- Flyway migration을 자동으로 역실행하지 않는다.
- DB 변경은 expand/contract와 하위 호환 정책을 사용한다.
- 데이터 restore는 명시적 확인과 백업 검증 후 수동으로 수행한다.

## 9. AI·IoT와 Jetson

2026-07-31 기준 AI는 Jetson에 검증된 baseline으로 이미 설치되어 있고, Robot runtime
계약이 준비됐다. 현재 적용 구조는 AI와 IoT의 lifecycle을 분리한다.

```text
/home/e103/yolo-pipeline
-> aiot-ai.service
-> ROS 2 JSON contract v1
-> IoT OTA에서 변경하지 않음

iot/master
-> protected iot-vX.Y.Z tag
-> Robot-only package + checksum + required_ai_contract_version
-> protected manual iot_publish
-> IoT stable manifest 게시

Jetson boot
-> AI baseline service 시작
-> IoT stable manifest 확인
-> 새 Robot package만 download
-> checksum/compatibility/smoke
-> /opt/aiot/iot/current atomic switch
-> 실패 시 previous 유지
```

GPU 학습·TensorRT 변환은 비용과 시간이 크므로 protected manual Job으로 유지한다.
AI 모델 변경은 별도 승인 절차로 수행하며 `iot-v*` release에 포함하지 않는다.

## 10. 안전한 적용 순서

### Phase 0: 기준 보존

- 원격 fetch 후 브랜치 SHA 기록
- EC2 container/image/current.env/Compose 상태 기록
- 현재 정상 image와 복구 명령 확인
- 작업 중인 Frontend worktree를 수정하지 않고 별도 Infra worktree 사용

### Phase 1: 공통 CI와 브랜치

- [x] 파트 master workflow/rules 추가
- [x] 파트 master는 MR only, force push 금지
- [x] 파트 소유 경로 검사 추가
- [x] 검증 완료 뒤 `develop` 운영 배포 제거

### Phase 2: Manifest와 component release

- [x] Release Manifest schema·validator·atomic writer 구현
- [x] 파트별 immutable image tag 구현
- [x] 성공 release history 저장
- [x] Frontend/Backend 개별 deploy/verify/rollback 구현

### Phase 3: 실제 통합검사

- [x] 실제 앱 기반 integration Compose 작성
- [x] 신규 파트 + 현재 안정 상대 파트 조합
- [x] 초기 required smoke 구현
- [x] planned 기능은 non-blocking으로 표시

### Phase 4: 비차단 시범 운영

- [x] 후보 integration Job을 실제 파트 MR에서 실행
- [x] Front/Back 후보 성공과 cleanup 확인
- [x] 기존 dev Pipeline 정상 확인

### Phase 5: 실제 AWS 전환 검증

- [x] Frontend 정상 배포와 강제 실패 rollback
- [x] Backend 정상 배포, Flyway V1~V5, 강제 실패 rollback
- [x] 다른 component와 MySQL·MQTT가 재시작되지 않았는지 확인
- [x] Release Manifest와 실제 container image 일치 확인

### Phase 6: 활성화

- [x] master MR 후보 통합검사를 blocking으로 활성화
- [x] 파트 master merge CD 활성화
- [x] 기존 `deploy_develop` 운영 자동 배포 비활성화
- [x] develop 통합과 root master 릴리스 절차 문서화

### Phase 7: AI·IoT 후속

- [x] Robot ROS 2 JSON v1 계약과 무구동 runtime 준비
- [x] `aiot-ai.service`, ROS setup wrapper, 실제 READY startup probe 구현
- [x] Robot-only `iot-v*` package, checksum, compatibility manifest 구현
- [x] AI 장애 시 Robot LIMITED mode를 위한 Wants/After 결합
- [ ] 실제 Jetson에서 AI service READY와 정상/동일/offline/checksum/smoke/rollback 검증

## 11. 예상 수정 파일

```text
.gitlab-ci.yml
infra/ci/**                         # 공통 template을 분리할 경우
infra/compose/compose.integration.yaml
infra/scripts/deploy.sh
infra/scripts/rollback.sh
infra/scripts/health-check.sh
infra/scripts/integration-test.sh
infra/scripts/release-manifest.sh
infra/scripts/validate-release-manifest.py
infra/release/release-manifest.schema.json
infra/OPERATIONS.md
infra/HANDOFF.md
infra/README.md
```

현재 `compose.application.yaml`과 `compose.infrastructure.yaml`의 책임 분리는 유지한다.
전체 파일을 한 번에 다시 작성하지 말고 기존 component-aware 배포 로직을 확장한다.

## 12. 완료 조건

Frontend/Backend 전환 완료 조건:

- [x] 기존 `front/dev`, `back/dev` CI가 정상 동작한다.
- [x] AI/IoT 코드가 없을 때 관련 Job은 실패가 아니라 skip/non-blocking이다.
- [x] `front/master` 후보가 현재 안정 Backend와 실제 통합검사를 통과한다.
- [x] `back/master` 후보가 현재 안정 Frontend와 실제 통합검사를 통과한다.
- [x] Frontend master 배포가 Frontend만 교체한다.
- [x] Backend master 배포가 Backend만 교체한다.
- [x] 실패 시 해당 component만 이전 image로 자동 복구한다.
- [x] 선택한 이전 component release로 수동 롤백할 수 있다.
- [x] Release Manifest와 실제 실행 image가 일치한다.
- [ ] DB migration 실패 시 Backend 배포가 중단되고 기존 서비스가 유지된다.
- [x] integration test의 임시 container와 volume이 항상 정리된다.
- [x] `develop` push가 운영 앱을 자동 배포하지 않는다.
- [ ] develop 통합은 마지막 배포 성공 release만 사용한다.
- [x] 운영자가 서버 SSH 없이 GitLab에서 정상 배포 상태를 확인할 수 있다.

최초 develop 통합에서 현재 파트 master의 전환 전 `.gitlab-ci.yml`과 충돌하는 것은
예상된 안전장치다. `infra/CICD_V2_OPERATIONS.md` 절차대로 최신 `infra/dev` 정책을
보존하고, 삭제된 develop 배포 Job이 다시 생기지 않았는지 검사해야 한다.

AI/IoT 후속 완료 조건:

- [x] IoT version, checksum, AI contract compatibility metadata가 생성된다.
- [x] protected manual 승인 전에는 stable manifest가 변경되지 않는다.
- [x] IoT archive가 AI runtime과 모델을 포함하지 않는다.
- [x] Jetson updater가 부팅 시 Robot component만 갱신하도록 분리됐다.
- [ ] 실제 Jetson에서 network/checksum/compatibility/smoke 실패 시 마지막 정상 버전 유지 검증

## 13. 다음 작업자가 가장 먼저 할 일

1. `infra/CICD_V2_OPERATIONS.md`의 통합 마일스톤 절차로 첫 `develop` 통합 MR을 만든다.
2. 파괴적인 Flyway migration을 만들기 전에 별도 실패 migration으로 자동 중단을 검증한다.
3. `iot/feat/robot-runtime`을 `iot/dev`와 `iot/master`로 MR 병합한다.
4. AI `yolo_pipeline.main`에 ROS JSON v1 publisher/control adapter를 연결한다.
5. 실제 Jetson에서 AI READY와 IoT boot/update/offline/checksum/smoke/rollback을 검증한다.

## 14. 하지 말아야 할 것

- 작업 중인 다른 파트 worktree를 reset, clean, checkout하지 않는다.
- 보호 브랜치를 force push하지 않는다.
- 처음부터 모든 예정 API를 blocking test로 만들지 않는다.
- `develop`과 파트 master가 같은 운영 서비스에 모두 자동 배포되게 하지 않는다.
- 통합 테스트와 다른 image를 운영에 다시 build해 배포하지 않는다.
- AI/IoT master merge만으로 Jetson stable channel을 자동 갱신하지 않는다.
- 자동 DB down migration이나 무검증 restore를 수행하지 않는다.
- GitLab token, SSH key, DB/MQTT password를 commit 또는 Pipeline log에 출력하지 않는다.

예상 소요는 Frontend/Backend 전환 약 7~10시간, 실제 AI/IoT 코드가 준비된 뒤 파트별
패키지·OTA 확장 약 4~8시간이다.
