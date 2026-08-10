# Back 순찰 경로·Navigation Config 인수인계

## 작업 기준

- 작업 브랜치: `back/feat/ordered-waypoint-config-clean`
- 기준 브랜치/커밋: `origin/back/dev` / `a6b10cc`
- 병합 대상: `back/dev` 검증 후 `back/master`
- 이름이 비슷한 `back/feat/ordered-waypoint-config` worktree에는 다른 작업자의 대량 변경이 있어 사용하지 않았다.

## 변경 내용

1. 지도별 순서 있는 waypoint 저장 모델과 V15 migration을 추가했다.
2. 관리자용 waypoint 전체 교체/조회 API를 추가했다.
3. Robot service token 전용 navigation config 조회 API를 추가했다.
4. 구역 저장을 append에서 지도 단위 atomic replace로 변경했다.
5. 지도 재업로드 또는 구역 교체 시 오래된 waypoint와 활성 구역이 남지 않도록 무효화한다.
6. 순찰 시작 전에 현재 map/version의 경로 정합성을 잠금 상태에서 검사한다.
7. MQTT 발행 실패와 ACK 경쟁 상황에서 순찰 상태가 잘못 남는 경우를 보강했다.

## 주요 파일

- `backend/src/main/resources/db/migration/V15__create_navigation_waypoints.sql`
- `backend/src/main/java/com/oneloop/map/domain/NavigationWaypoint.java`
- `backend/src/main/java/com/oneloop/map/domain/NavigationWaypointAction.java`
- `backend/src/main/java/com/oneloop/map/repository/NavigationWaypointRepository.java`
- `backend/src/main/java/com/oneloop/map/service/NavigationWaypointService.java`
- `backend/src/main/java/com/oneloop/map/service/RobotNavigationConfigService.java`
- `backend/src/main/java/com/oneloop/map/service/NavigationConfigurationGuard.java`
- `backend/src/main/java/com/oneloop/map/controller/WaypointController.java`
- `backend/src/main/java/com/oneloop/map/controller/RobotNavigationController.java`
- `backend/src/main/java/com/oneloop/map/service/ZoneService.java`
- `backend/src/main/java/com/oneloop/map/service/MapService.java`
- `backend/src/main/java/com/oneloop/patrol/service/PatrolCommandStateService.java`
- `backend/src/main/java/com/oneloop/patrol/service/PatrolCommandService.java`

## API 계약

### 관리자 API

- `GET /api/map/{mapId}/waypoints`
- `PUT /api/map/{mapId}/waypoints`
- `PUT /api/map/{mapId}/zones`
- 로그인 관리자의 apartment와 map 소유 관계를 검사한다.
- PUT 요청은 현재 `mapVersion`과 전체 배열을 받으며, 성공 시 기존 항목을 교체한다.

### Robot API

- `GET /api/robot/navigation-config`
- `ROLE_ROBOT`만 접근할 수 있다.
- 토큰 principal의 robotId로 삭제되지 않은 로봇과 apartment, 최신 map을 찾는다.
- 응답은 `schemaVersion: 1`, map metadata, 활성 zones, ordered waypoints를 포함한다.

```json
{
  "schemaVersion": 1,
  "map": {
    "mapId": 1,
    "mapVersion": 3,
    "mapName": "demo",
    "resolution": 0.05,
    "originX": 0.0,
    "originY": 0.0,
    "originYaw": 0.0,
    "width": 100,
    "height": 100
  },
  "zones": [],
  "waypoints": []
}
```

## 데이터 정합성

- waypoint sequence는 1..N으로 연속이어야 한다.
- 마지막 지점 하나만 `DESTINATION`이어야 한다.
- `x`, `y`, `action`은 필수다.
- 좌표는 origin과 originYaw를 반영한 지도 범위 안이어야 한다.
- acceptance radius는 0.20~1.00m이며 미지정 시 0.30m다.
- 연속 waypoint 거리는 두 acceptance radius 합보다 커야 한다.
- zone 참조는 현재 map/version의 활성 구역만 허용한다.
- 진행 중 또는 STOP 요청 중인 순찰에서는 지도/구역/경로 변경을 거부한다.
- 구역 교체는 waypoint를 먼저 제거하고 기존 checkpoint를 비활성화한 뒤 새 구역을 저장한다.
- 지도 재업로드도 waypoint 제거와 기존 zone 비활성화를 같은 트랜잭션에서 수행한다.
- 기존 순찰 이력의 checkpoint FK를 보존하기 위해 checkpoint는 물리 삭제하지 않는다.

## 순찰 시작 보강

- START 처리 시 robot과 map을 잠그고 현재 route를 검사한 후 patrol과 MQTT 명령을 만든다.
- 활성 순찰의 중복 START를 막는다.
- MQTT 발행 실패는 별도 트랜잭션에서 상태를 보상한다.
- 완료 판정은 마지막 ordered `DESTINATION`의 좌표와 acceptance radius를 사용한다.

## 검증 결과

- 실행 환경: `JAVA_HOME=D:\codex\toolchains\jdk-21`
- 명령: `gradlew.bat test --no-daemon --rerun-tasks`
- 결과: 19 suites, 79 tests, 실패/오류/skip 0.
- 시스템 기본 JDK 25에서는 Gradle Java 21 toolchain을 찾지 못했으며, 프로젝트용 JDK 21 지정 후 전체 성공했다.

## 다음 작업자 확인 사항

- 개발 DB 백업 후 V15를 적용하고 기존 checkpoint의 `active=true` 기본값과 인덱스를 확인한다.
- Back을 먼저 dev 환경에 반영한 뒤 Front 저장/조회와 Robot navigation-config E2E를 확인한다.
- 운영 DB migration은 이 브랜치 작업 중 실행하지 않았다.
- 서비스 토큰, DB 비밀번호, JWT 등의 값은 문서에 기록하지 않는다.
