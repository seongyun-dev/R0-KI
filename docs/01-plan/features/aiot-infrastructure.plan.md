# AIoT Infrastructure - Plan Document

> Version: 1.0.0 | Date: 2026-07-20 | Status: Draft
> Level: Enterprise | Owner: Infra

---

## 1. Overview

### 1.1 Purpose

AI 기반 스마트 아파트 순찰 시스템의 모든 파트가 정해진 계약에 맞춰 코드를 올리면 자동으로 검사, 빌드, 패키징, 배포할 수 있는 공통 인프라를 구축한다.

대상은 EC2의 Frontend/Backend 런타임뿐 아니라 GitLab CI/CD, GPU 서버의 AI 학습·변환 경로, Jetson Orin Nano의 AI/IoT 통합 Pull OTA, 보안·백업·관측·롤백까지 포함한다.

### 1.2 Background

- 저장소는 `frontend/`, `backend/`, `ai/`, `robot/`, `infra/`를 포함하는 모노레포다.
- 파트별 `*/dev` 브랜치를 공용 `develop`에 통합하고 `master`를 안정 release 기준으로 사용한다.
- EC2에는 GitLab Runner, MySQL, 인증 기반 Mosquitto, 일일 로컬 백업이 이미 가동 중이다.
- Frontend/Backend 컨테이너 배포, 앱용 HTTPS, GPU 파이프라인, Jetson Pull OTA는 아직 완성되지 않았다.
- 코드가 준비되지 않은 파트도 인프라 구축을 막지 않도록 smoke fixture와 조건부 CI를 사용한다.

## 2. Goals

### 2.1 Primary Goals

- [ ] 코드가 없어도 전체 CI/CD 배관을 검증할 수 있는 Platform Ready 상태를 만든다.
- [ ] Frontend와 Backend를 독립적으로 검사·빌드하고 하나의 조정된 EC2 CD로 배포한다.
- [ ] AI와 IoT를 각각 검사한 뒤 승인된 조합만 Jetson 통합 release로 발행한다.
- [ ] GPU Device3에서 실행되는 AI 학습·변환 job을 일반 CI와 분리한다.
- [ ] Jetson이 부팅 시 승인된 release를 Pull하고, 오프라인·손상·실행 실패 시 이전 정상 버전으로 복구하게 한다.
- [ ] secret, 인증서, 데이터, 로그, 백업, 모니터링, 장애 대응 절차를 운영 가능한 수준으로 문서화한다.

### 2.2 Non-Goals

- Frontend/Backend의 비즈니스 기능 구현
- AI 모델의 정확도 개선과 학습 데이터 관리
- ROS2 순찰·센서·제어 알고리즘 구현
- Jenkins, AWS IoT Core, RDS, ECR, Kubernetes 도입
- 단일 EC2를 staging/production 두 서버로 물리 분리
- 승인되지 않은 merge를 Jetson에 즉시 배포

## 3. Fixed Platform Contracts

### 3.1 Frontend

- 경로: `frontend/`
- 기본 환경: React + Vite, Node 20, npm
- 필수 파일: `package.json`, `package-lock.json`
- 표준 명령: `npm ci`, `npm run lint --if-present`, `npm run test --if-present`, `npm run build`
- 기본 산출물: `dist/`
- 런타임: Nginx 정적 배포, 컨테이너 포트 80
- API 접근: 동일 origin의 `/api`
- readiness: `GET /`

실제 프로젝트가 CRA 등 다른 React 빌드 도구를 사용하면 산출물 adapter만 조정하고 EC2·CI 계약은 유지한다.

### 3.2 Backend

- 경로: `backend/`
- 환경: Java 21, Gradle Wrapper, Spring Boot
- 표준 명령: `./gradlew test`, `./gradlew bootJar`
- 런타임 포트: 8080
- readiness: 최종 `/actuator/health`, 초기 fallback `/swagger-ui.html`
- 데이터베이스: `aiot-mysql:3306`, Flyway forward migration
- MQTT: `aiot-mosquitto:1883`
- 영속 경로: `/app/data/uploads`, `/app/data/maps`
- secret과 운영 설정: `/srv/aiot/secrets/backend.env`

### 3.3 AI and IoT

- AI 경로: `ai/`; IoT 경로: `robot/`
- 각 파트는 의존성 정의, test, install, run, smoke-test 진입점을 제공한다.
- 일반 CI는 CPU에서 가능한 정적 검사와 단위 테스트만 수행한다.
- GPU 학습·변환은 `ai-gpu-device3` 전용 Runner의 수동 job으로 제한한다.
- Jetson release는 AI 코드, IoT 코드, 모델, manifest를 하나의 호환 버전으로 묶는다.

### 3.4 Release and Branch Policy

```text
feature -> part/dev -> develop -> master
```

- feature MR: 해당 파트 CI
- part/dev -> develop MR: 변경 파트 CI + 통합 검증
- develop push: Frontend/Backend EC2 자동 배포
- master push: EC2 수동 안정 배포
- `jetson-vX.Y.Z` tag 또는 승인된 manual job: Jetson stable release 발행
- `part/dev`, `develop`, `master` 직접 push와 force push 금지

## 4. Scope and Workstreams

### WS0. Safety Baseline and Contract Freeze

- 현재 EC2 서비스, 포트, 파일, 백업, 인증서, Runner 상태를 기준선으로 기록한다.
- 기존 Gerrit 8988/29418, Apache 8989, 기본 Nginx, legacy MQTT 1883의 변경 금지 경계를 고정한다.
- `infra/CONTRACTS.md`에 파트별 실행 계약과 소유 경로를 문서화한다.
- 배포 리허설 전까지 `DEPLOY_FREEZE=true`를 적용하거나 demo 브랜치에서만 수동 배포한다.

**완료 기준**

- [ ] 기준선과 변경 금지 대상이 문서화됨
- [ ] secret이 Git과 CI 로그에 없음을 확인
- [ ] 파트별 최소 계약이 공유됨

### WS1. EC2 Platform Ready

- 기존 MySQL/Mosquitto Compose와 `aiot-network`를 재검증한다.
- Nginx HTTPS 설정과 `/infra-health`를 애플리케이션 없이도 검증 가능하게 한다.
- 인증서 동기화, 로그 rotation, 디스크 사용량 확인을 자동화한다.
- 백업 생성·checksum·복구 절차를 검증하고 외부 백업은 후속 항목으로 분리한다.
- 인프라 smoke fixture를 `infra/smoke/`에 격리한다.

**완료 기준**

- [ ] MySQL healthy 및 호스트 3306 미공개
- [ ] MQTT 인증 round-trip 및 TLS 8883 성공
- [ ] HTTPS `/infra-health` 성공
- [ ] smoke 컨테이너 배포·health·제거 성공
- [ ] 일일 백업과 검증 가능한 checksum 존재

### WS2. GitLab CI Foundation

- stages를 `validate -> test -> build -> package -> deploy -> verify`로 정리한다.
- `frontend_ci`, `backend_ci`, `ai_ci`, `iot_ci`, `infra_validate`를 경로 기반으로 실행한다.
- 코드가 없는 파트는 실패하지 않고 명시적으로 skip한다.
- Dockerfile이 있는 파트는 image build 검증까지 수행한다.
- Shell Runner의 Docker 권한을 고려해 프로젝트 잠금, tag, 동시 실행 제한, 배포 `resource_group`을 유지한다.
- CI/CD 파일과 `infra/**`, `**/Dockerfile`에 Infra 리뷰 규칙을 적용한다.

**완료 기준**

- [ ] smoke fixture로 validate/test/build pipeline 통과
- [ ] 각 파트 경로 변경 시 해당 job만 실행
- [ ] code/manifest 부재가 다른 파트 CI를 막지 않음
- [ ] secret이 CI 출력에 노출되지 않음

### WS3. Frontend/Backend EC2 CD

- Frontend는 React multi-stage Dockerfile과 SPA Nginx 설정을 제공한다.
- Backend는 Java 21 multi-stage Dockerfile을 제공한다.
- CI는 두 image를 독립적으로 빌드하되 CD는 하나의 배포 조정 job과 lock을 사용한다.
- 변경된 component만 새 image로 빌드하고 변경되지 않은 component의 현재 image tag를 유지한다.
- 첫 배포 시 준비된 component만 기동할 수 있게 현재의 "Dockerfile 둘 다 필요" 조건을 제거한다.
- 배포 manifest에 Frontend/Backend image와 commit을 각각 기록한다.
- 배포 후 health check 실패 시 마지막 정상 조합으로 rollback한다.

**완료 기준**

- [ ] Backend 단독 첫 배포 가능
- [ ] Frontend가 추가된 뒤 두 서비스 통합 배포 가능
- [ ] 3000/8080은 loopback에만 bind
- [ ] HTTPS `/`, `/api/`, application health 성공
- [ ] 의도적으로 실패한 image에서 자동 rollback 성공
- [ ] 재부팅 후 컨테이너 자동 복구

### WS4. AI/GPU Pipeline

- GPU 서버 Device3에 프로젝트 전용 Runner를 설치하거나 안전한 원격 job 실행 방식을 확정한다.
- Runner tag를 `ai-gpu-device3`로 제한하고 일반 job 및 untagged job 실행을 차단한다.
- `ai_ci`와 `ai_train`/`ai_convert`를 분리한다.
- 모델 원본, ONNX, TensorRT artifact의 버전·checksum·호환 정보를 manifest에 기록한다.
- 학습은 manual pipeline으로만 수행하고 운영 요청은 GPU 서버가 직접 처리하지 않는다.

**완료 기준**

- [ ] GPU smoke job에서 할당 장치만 인식
- [ ] 승인된 수동 job만 학습·변환 실행
- [ ] 모델 artifact와 checksum 생성
- [ ] CUDA/TensorRT/JetPack 호환 정보 기록

### WS5. Jetson Pull OTA

- `infra/jetson/`에 updater, systemd unit, manifest schema를 구현한다.
- `infra/scripts/package-jetson-release.sh`로 AI+IoT+모델 통합 bundle을 만든다.
- `jetson_validate`, `jetson_package`, `jetson_publish` job을 추가한다.
- GitLab Generic Package Registry와 Jetson 전용 read-only Deploy Token을 사용한다.
- Jetson 설치 경로를 `/opt/aiot/releases/<version>`으로 버전화하고 `current`/`previous` symlink를 원자적으로 전환한다.
- 네트워크 불가, checksum 불일치, 호환성 실패, smoke 실패 시 마지막 정상 버전을 실행한다.

**완료 기준**

- [ ] 승인되지 않은 merge가 stable manifest를 변경하지 않음
- [ ] 동일 버전 재다운로드 없음
- [ ] 정상 release 설치 및 서비스 기동
- [ ] 오프라인 부팅 시 기존 정상 버전 기동
- [ ] 손상 bundle과 smoke 실패에서 자동 rollback
- [ ] token과 MQTT credential이 Git/로그에 노출되지 않음

### WS6. Integration, Security, and Operations

- Jetson의 MQTT TLS 8883 command/status/heartbeat/reconnect를 검증한다.
- 성공 후 legacy `hanbakwi-mosquitto`와 외부 1883을 제거한다.
- AWS Security Group의 22/443/8883 source와 3306/3000/8080 차단을 확인한다.
- 로그·디스크·인증서 만료·컨테이너 health 모니터링과 알림을 추가한다.
- 외부 암호화 백업 대상과 retention을 정하고 복구 훈련을 수행한다.
- 운영 Runbook과 시연 체크리스트를 최신화한다.

**완료 기준**

- [ ] 외부 1883 제거 및 8883 제한
- [ ] 3306/3000/8080 외부 접근 불가
- [ ] 인증서 만료 사전 알림
- [ ] 외부 백업과 복구 시험
- [ ] 장애·롤백·인증서 갱신 Runbook 검증

## 5. Milestones and Schedule

| Milestone | Target | Deliverable | Status |
| --- | --- | --- | --- |
| M0 Plan/Design | 2026-07-20 | 계약, 아키텍처, 안전 경계 확정 | In Progress |
| M1 Platform Demo | 2026-07-21 | EC2/Runner/CI/smoke 배포/health/rollback 증거 | Pending |
| M2 App Onboarding | 코드 확보 후 T+1 | 실제 Frontend/Backend CI 및 EC2 배포 | Pending |
| M3 GPU Pipeline | GPU 접근 확정 후 T+1~2 | GPU Runner, 모델 artifact와 manifest | Pending |
| M4 Jetson OTA | AI/IoT entrypoint 확정 후 T+2~3 | Package Registry, updater, systemd, rollback | Pending |
| M5 Operational Ready | 최종 배포 전 | 보안, 외부 백업, 모니터링, Runbook | Pending |

### M1 Demonstration Evidence

- GitLab Pipeline URL과 통과 job
- Runner online/valid 상태
- smoke image의 commit SHA tag
- EC2 컨테이너 및 포트 상태
- HTTPS health 응답
- 의도적 실패 배포와 자동 rollback 로그
- MySQL/MQTT health 및 백업 timer

M1은 Platform Ready 증명이며 실제 파트 코드의 Workload Verified 완료로 과장하지 않는다.

## 6. Dependencies and Gates

```text
WS0 -> WS1 -> WS2 -> WS3
              |      |
              |      -> Frontend/Backend actual code onboarding
              |
              -> WS4 -> WS5 -> WS6
```

- WS1/WS2는 애플리케이션 코드 없이 진행 가능하다.
- WS3 구조와 smoke 검증은 코드 없이 가능하지만 실제 앱 health 검증에는 코드가 필요하다.
- WS4 구조는 코드 없이 가능하지만 실제 모델 생성에는 AI 코드와 GPU 접근이 필요하다.
- WS5 updater와 더미 bundle 검증은 코드 없이 가능하지만 실제 장비 검증에는 Jetson 접근과 AI/IoT entrypoint가 필요하다.
- destructive 변경인 legacy 1883 제거와 데이터 복구는 명시적 검증 gate 이후에만 실행한다.

## 7. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
| --- | --- | --- | --- |
| 미완성 코드가 develop 자동 배포를 촉발 | High | High | DEPLOY_FREEZE/demo branch, component 존재·health gate |
| 현재 CI 성공이 실제 배포 성공으로 오인됨 | High | High | skip 상태 명시, deploy evidence와 Workload Verified 분리 |
| Frontend/Backend 버전 조합 불명확 | High | Medium | component별 commit/image를 배포 manifest에 기록 |
| Shell Runner를 통한 EC2 root 수준 권한 노출 | Critical | Medium | project lock, tagged only, protected branch, Infra review |
| DB migration 후 앱 rollback 불가 | High | Medium | forward-compatible migration, 배포 전 backup, 자동 DB rollback 금지 |
| GPU/Jetson 환경 차이 | High | High | manifest에 JetPack/CUDA/TensorRT/arch 기록, smoke gate |
| OTA 중 전원·네트워크 장애 | High | Medium | 임시 다운로드, checksum, atomic symlink, offline fallback |
| local-only backup으로 EC2 손실 미보호 | High | Medium | 외부 암호화 backup과 복구 훈련 |
| 인증서 수동 갱신 누락 | High | Medium | 만료 모니터링, 갱신 Runbook, 가능 시 DNS API 자동화 |
| 기존 Gerrit/Apache/MQTT 손상 | Critical | Low | 변경 금지 목록, 사전 backup, 포트·서비스 검증 |

## 8. Definition of Done

### 8.1 Platform Ready

- [ ] 코드가 없는 상태에서도 smoke fixture로 CI build/deploy/verify/rollback이 재현됨
- [ ] 각 파트 계약과 조건부 CI가 문서화됨
- [ ] EC2 인프라, secret, TLS, backup, health가 정상
- [ ] 실제 코드가 올라오면 adapter 수정만으로 onboarding 가능

### 8.2 Workload Verified

- [ ] 실제 Frontend/Backend가 EC2에서 HTTPS로 동작
- [ ] 실제 AI/IoT test와 Jetson release packaging 성공
- [ ] GPU artifact와 Jetson 호환 manifest 생성
- [ ] Jetson OTA의 정상/동일/오프라인/손상/rollback 시나리오 통과
- [ ] 운영 보안, 외부 backup, monitoring, Runbook 검증 완료

## 9. Deliverables

- `infra/CONTRACTS.md`
- `.gitlab-ci.yml` 및 필요 시 `.gitlab/ci/*.yml`
- Frontend/Backend Dockerfile과 `.dockerignore`
- component-aware deploy/health/rollback 스크립트
- `infra/smoke/` fixture
- `infra/jetson/` updater와 systemd unit
- Jetson manifest schema와 release package script
- GitLab Generic Package Registry publish job
- GPU Runner 운영 절차
- 보안·backup·monitoring·release Runbook
- 완료 증거와 gap analysis/report

## 10. References

- `infra/HANDOFF.md`
- `infra/OPERATIONS.md`
- `infra/README.md`
- `.gitlab-ci.yml`
- `infra/compose/compose.infrastructure.yaml`
- `infra/compose/compose.application.yaml`
