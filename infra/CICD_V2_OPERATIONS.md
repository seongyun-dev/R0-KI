# 파트별 독립 CI/CD 운영 가이드

기준일: 2026-07-23 (Asia/Seoul)

이 문서는 `infra/cicd-v2`에서 구현한 파트별 master 배포 방식의 기준 문서다.
코드는 구현·격리 검증되었지만, 보호 브랜치에 MR로 병합되기 전까지 GitLab의 실제
배포 규칙은 기존 `develop` 중심 방식이다.

## 1. 최종 브랜치와 배포 규칙

```text
feature
  -> 파트/dev        빠른 파트 CI, 배포 없음
  -> 파트/master     후보 통합 테스트 후 해당 파트만 자동 배포
  -> develop         검증된 파트 release 조합을 기록하는 통합 브랜치
  -> root master     발표·최종 마일스톤, 수동 승인
```

| 브랜치 | 자동 동작 |
| --- | --- |
| `front/dev` | npm ci, lint/test/build |
| `back/dev` | Java 21 Gradle test |
| `front/master` MR/push | Front 후보 이미지 + 현재 안정 Back + 임시 MySQL/MQTT/Nginx 통합 테스트 |
| `front/master` push | 통합 테스트를 통과한 Front만 자동 배포 |
| `back/master` MR/push | Back 후보 이미지 + 현재 안정 Front + 임시 MySQL/MQTT/Nginx 통합 테스트 |
| `back/master` push | 통합 테스트를 통과한 Back만 자동 배포 |
| `develop` | 전환 완료 뒤 통합 검증 전용; 운영 자동 배포 없음 |
| root `master` | 최종 마일스톤 수동 배포 |

`front/master` 배포는 Backend·MySQL·Mosquitto를 재시작하지 않는다. `back/master`
배포도 Frontend를 재시작하지 않는다. 두 배포는 같은 `aiot-ec2-deploy`
resource group을 사용하므로 동시에 운영 상태를 변경하지 않는다.

## 2. Pipeline 동작

Frontend 예시:

```text
front/dev -> front/master MR
  -> frontend_ci
  -> aiot-frontend:front-<commit> 생성
  -> 후보 Front + 현재 안정 Back 통합 테스트
  -> 성공한 MR만 merge

front/master push
  -> 같은 commit 이미지 재확인
  -> 같은 통합 테스트 재실행
  -> Front 컨테이너만 교체
  -> readiness 검사
  -> release-manifest.json 갱신
  -> 실패 시 Front만 이전 버전으로 자동 복구
```

Backend도 `aiot-backend:back-<commit>`과 동일한 순서로 동작한다. GitLab 화면의
`production/frontend`, `production/backend` Environment에서 최근 배포를 각각
확인할 수 있다.

## 3. 실제 통합 테스트 범위

`infra/scripts/integration-test.sh`는 운영 DB를 사용하지 않는다. Pipeline마다 다음
격리 구성을 새로 만들고 종료 시 volume과 함께 제거한다.

```text
후보 component image + 현재 운영 중인 상대 component image
  -> 임시 Nginx
  -> 임시 MySQL 8.4
  -> 임시 Mosquitto 2
```

현재 필수 검증:

1. 실제 Front/Back 이미지 기동
2. Nginx `/`, `/api/`, OpenAPI·Swagger 경로
3. MySQL 연결과 Flyway migration 이력 생성
4. MQTT publish/subscribe 왕복
5. 미인증 보호 API가 401을 반환하는지 확인
6. Backend에 signup 계약이 있으면 회원가입→로그인→JWT→로봇 목록까지 확인
7. 새 Front 이미지에 개발용 `http://localhost:8080` 설정이 남지 않았는지 확인
8. 실패 로그 출력과 임시 컨테이너·DB 정리

아직 Backend 안정 버전에 없는 API를 Front 배포의 필수 조건으로 만들지 않는다.
OpenAPI에 기능이 생기면 해당 검사를 required로 승격한다.

2026-07-23 격리 검증 결과:

- 현재 운영 Front + 현재 운영 Back: 통과
- `front/dev` 후보 `8dc13a4be2c7` + 현재 운영 Back: 통과
- 현재 운영 Front + `back/dev` 후보 `e9fa069d81ff`: signup/JWT/Robot 포함 통과

## 4. Front 운영 빌드 계약

운영 Front 이미지는 앱 소스의 기본 Dockerfile 대신
`infra/docker/frontend.Dockerfile`로 빌드한다.

- Node 20
- `package-lock.json`과 `npm ci` 사용
- `node_modules`는 Git에 저장하지 않음
- `VITE_USE_MOCKS=false`
- `VITE_API_BASE_URL=`: 브라우저가 동일 도메인의 `/api`를 사용

파트 개발용 `.env`의 mock 설정은 바꾸지 않으며, 운영 이미지에서만 강제한다.

## 5. Release Manifest

운영 상태의 source of truth:

```text
/srv/aiot/deploy/release-manifest.json
/srv/aiot/deploy/releases/<release-id>.json
```

Manifest에는 Front/Back의 enabled 상태, 불변 image, commit, branch, DB schema,
AI/IoT 상태, Infra commit, pipeline/job ID, 통합 검증 상태가 들어간다. 비밀번호나
토큰은 저장하지 않는다. 성공한 readiness 검사 뒤에만 atomic replace로 현재
Manifest를 바꾸며 모든 성공 release를 별도 파일로 남긴다.

조회:

```bash
sudo python3 /srv/aiot/deploy/release-manifest.py validate \
  /srv/aiot/deploy/release-manifest.json
sudo cat /srv/aiot/deploy/release-manifest.json
sudo ls -1t /srv/aiot/deploy/releases | head
```

## 6. 롤백

배포 중 Compose/readiness/Manifest 기록이 실패하면 이번에 변경한 component만
직전 상태로 자동 복구한다. 수동 롤백은 다음과 같다.

```bash
# 기록된 release의 Front만 복구
sudo /srv/aiot/deploy/rollback.sh frontend <release-id>

# 기록된 release의 Back만 복구
sudo /srv/aiot/deploy/rollback.sh backend <release-id>

# 검증된 Front+Back 조합 전체 복구
sudo /srv/aiot/deploy/rollback.sh release <release-id>

# 불변 image를 직접 지정할 수도 있음
sudo /srv/aiot/deploy/rollback.sh frontend aiot-frontend:front-<commit>
sudo /srv/aiot/deploy/rollback.sh backend aiot-backend:back-<commit>
```

Back 이미지 롤백은 DB down migration을 실행하지 않는다. Flyway 변경은 이전 앱도
동작하는 expand/contract 방식으로 작성해야 하며 데이터 restore는 백업 검토 후
수동으로만 한다.

## 7. 팀 작업 방법

일상 개발:

1. `파트/dev`에서 feature 브랜치를 만든다.
2. feature를 `파트/dev` MR로 병합하고 파트 CI를 통과시킨다.
3. 배포할 기능이 모이면 `파트/dev -> 파트/master` MR을 만든다.
4. 후보 통합 테스트 성공과 리뷰를 확인하고 merge한다.
5. merge 뒤 해당 파트 자동 배포와 Environment 상태를 확인한다.

통합 마일스톤:

1. Release Manifest에서 마지막으로 배포 성공한 각 파트 commit을 선택한다.
2. 선택한 `파트/master` release를 release/integration 브랜치에 순서대로 합친다.
3. 전체 계약·통합 테스트 뒤 `develop` MR로 기록한다.
4. 단순히 각 master 최신 HEAD를 무조건 develop에 넣지 않는다.

## 8. 안전한 활성화 순서

1. `infra/cicd-v2 -> infra/dev` MR과 Infra Pipeline을 통과시킨다.
2. 공통 Infra 커밋을 정상 MR로 `front/dev`, `back/dev`에 동기화한다.
3. `front/dev -> front/master`, `back/dev -> back/master` MR을 각각 만든다.
4. 후보 통합 테스트가 성공한 파트부터 master에 merge한다.
5. 실제 자동 배포 후 container image와 Release Manifest가 일치하는지 확인한다.
6. Front/Back 개별 배포와 강제 실패 자동 롤백을 각 1회 검증한다.
7. 그 뒤에만 기존 `deploy_develop` 자동 운영 배포를 비활성화한다.

이 브랜치에서는 1~6 검증 전 서비스 공백을 막기 위해 기존 `develop` 자동 배포를
아직 유지한다. 따라서 MR 병합 직후 별도 전환 커밋에서 7번을 수행해야 한다.

## 9. 아직 남은 범위

- 보호 브랜치 MR을 통한 실제 GitLab 활성화
- 첫 master 자동 배포 및 의도적 실패 롤백 검증
- `develop` 운영 자동 배포 제거
- `infra/master` 공통 설정 수동 승인 정책 확정
- AI/IOT 실제 코드 계약 확정 후 파트별 package/checksum 게시
- 승인된 AI+IoT 조합만 Jetson stable manifest로 승격
- Jetson 실장비 boot/update/offline/checksum/smoke/rollback 검증

AI/IOT master merge는 EC2 앱을 배포하지 않고 artifact만 만든다. Jetson은 승인된
stable manifest를 부팅 시 확인해 필요한 package만 Pull OTA로 갱신한다.

## 10. 비밀값과 긴급 중지

비밀값은 `/srv/aiot/secrets`에만 두고 Pipeline 로그·Manifest·Git에 넣지 않는다.
배포를 긴급 중지할 때 GitLab CI/CD 변수 `DEPLOY_FREEZE=true`를 설정하면 master와
기존 develop 배포 Job이 실행되지 않는다. 이미 실행 중인 배포는 서버의
`/srv/aiot/deploy/deploy.lock`으로 중복 실행이 차단된다.
