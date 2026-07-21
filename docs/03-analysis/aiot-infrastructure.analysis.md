# Gap Analysis: aiot-infrastructure

> Date: 2026-07-21 | Design: `docs/02-design/features/aiot-infrastructure.design.md`

## Match Rate: 78%

저장소 수준의 구현 항목은 대부분 반영됐고, EC2 격리 검증도 통과했다. 구현은
`infra/dev` 커밋으로 인계한다. 다만 이번 설정의 실제 GitLab Pipeline,
`develop` 통합, 실제 파트 코드, GPU Runner, Jetson 실장비, AWS 정책과 외부
백업 대상이 없어 운영 완료로 볼 수 없는 항목을 gap으로 남겼다.

## Implemented Items

- [x] 파트별 계약과 코드 부재 시 skip/계약 누락 시 fail 정책
- [x] `validate -> test -> build -> package -> deploy -> verify` CI stage
- [x] Frontend/Backend/AI/IoT 경로 기반 CI
- [x] 격리 Frontend/Backend smoke image build, health, cleanup
- [x] component-aware 단독 최초 배포, 상태 보존, rollback
- [x] Frontend React/Vite/Nginx Docker 계약과 SPA fallback
- [x] Backend Java 21/Gradle 비-root Docker 계약
- [x] 실제 `back/dev` test와 image build 검증
- [x] MySQL/MQTT/certificate/application 통합 health check
- [x] loopback 3000/8080과 host Nginx `/`, `/api/`, `/infra-health`
- [x] stable Jetson manifest Nginx route와 immutable Package Registry URL
- [x] GPU Device3 manual job, 전용 tag, resource lock, 설치 runbook
- [x] Jetson manifest schema와 dependency-free validator
- [x] Robot/AI 통합 release, payload/artifact checksum, version manifest
- [x] protected tag package와 manual stable publish job
- [x] Pull updater의 JetPack/architecture/disk/checksum/archive 검증
- [x] versioned release와 atomic current/previous symlink 전환
- [x] Jetson systemd install/update/runtime unit
- [x] OTA 정상, 동일 버전, offline, checksum mismatch, rollback 격리 E2E
- [x] 원자적 local backup, checksum, completion marker, latest symlink
- [x] runtime/disk/backup/certificate periodic monitor와 timer
- [x] 운영·handoff·GPU 문서 갱신

## Validation Evidence

- EC2 runner 계정으로 Frontend/Backend 최초 배포와 첫 rollback 통과
- 정상 Frontend v1 이후 실패 v2에서 이전 image/env/Compose 자동 복구 통과
- `back/dev` Gradle test와 Java 21 image build 통과
- React Docker image `/healthz`, `/`, 임의 SPA route 통과
- Jetson 3개 synthetic release package와 HTTPS Pull E2E 통과
- checksum mismatch에서 current `jetson-v0.0.1` 유지 확인
- post-activation smoke 실패에서 previous release 복구 확인
- offline manifest 실패에서 current release 유지 확인
- Nginx/Compose/systemd/shell/JSON/YAML 정적 검증 통과
- EC2 monitor: runtime 정상, disk 4%, certificate 62일, legacy backup warning
- 임시 backup: MySQL dump, file/MQTT archive, checksum, completion marker 통과
- 외부 점검: 3306/3000/8080 차단, 1883/8883 공개 상태 확인

## Missing Items

- [x] 변경을 `infra/dev`에 commit/push
- [ ] 이번 설정을 사용하는 실제 GitLab Pipeline 통과
- [ ] `infra/dev -> develop` MR과 파트 branch 동기화
- [ ] 실제 Frontend 코드 adapter 확인 및 HTTPS `/` 배포
- [ ] 실제 Backend 첫 배포와 agreed readiness endpoint 확인
- [ ] GPU 서버 SSH/sudo 확보 후 project-locked Runner 설치와 환경 탐지
- [ ] AI train/convert 실제 script와 모델 manifest 검증
- [ ] Jetson 주소·계정 확보, 현재 runtime backup 후 updater 설치
- [ ] Jetson MQTT TLS 8883 command/status/heartbeat/reconnect E2E
- [ ] 성공 후 legacy `hanbakwi-mosquitto`와 외부 1883 제거
- [ ] AWS Security Group 22/443/8883 source 범위 증적
- [ ] 외부 암호화 백업 대상과 실제 restore drill
- [ ] Slack/Discord/메일 중 하나의 경보 transport 연결
- [ ] 운영 image digest pin과 dependency audit threshold 확정

## Changed Items (Deviations from Design)

- [x] archive 내부 manifest는 payload checksum을, 외부 stable manifest는 실제
  archive checksum을 기록한다. 자기 자신을 포함한 archive SHA의 순환을 피하기
  위한 의도적 분리다.
- [x] Backend readiness는 코드 소유 팀이 Actuator를 추가하기 전까지
  `/swagger-ui.html`을 fallback으로 유지한다.
- [x] Jetson updater timer는 만들지 않고 boot/maintenance용 oneshot만 제공한다.
  설계의 "주기 업데이트 기본 비활성" 원칙을 따른다.
- [x] GPU Device3는 초기 index 3을 사용하되 UUID protected variable 전환을
  runbook의 권장 최종 상태로 둔다.

## Recommendations

1. 현재 변경을 먼저 Infra MR로 검증하고 `develop`에 병합한다.
2. Backend를 우선 단독 배포해 live DB migration과 readiness를 확인한다.
3. Frontend 코드가 올라오면 Vite `dist` 여부만 확인하고 통합 HTTPS를 연다.
4. GPU와 Jetson은 접근 권한을 받은 뒤 runbook 순서대로 설치하고 기존 runtime을
   먼저 백업한다.
5. MQTT TLS 실장비 E2E 전에는 legacy 1883을 유지한다.
6. 외부 백업과 Security Group은 계정 권한을 받은 뒤 별도 변경 승인으로 수행한다.

## Next Steps

- [x] Infra 변경 commit/push
- [ ] Infra Pipeline 확인과 `infra/dev -> develop` MR
- [ ] 실제 Backend/Frontend deploy evidence
- [ ] GPU/Jetson access와 device E2E
- [ ] security/backup external evidence
- [ ] gap 수정 후 재분석; 90% 이상이면 completion report
