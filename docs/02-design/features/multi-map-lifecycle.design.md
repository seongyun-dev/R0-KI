# Multi-Map Lifecycle — Phase 0 Contract

> Status: Phase 0–4 done · Phase 5 next (FE)  
> Date: 2026-08-11 · Owner: Backend (with FE/IoT consumers)  
> Scope of this doc: policy + API/domain contracts. Phase 1–4 implement schema through patrol detail/PDF snapshot.

관련 현상: 단지당 맵을 덮어쓰면 과거 순찰·포인트가 **새 맵 좌표계** 위에 그려진다.  
목표는 **맵 생성 단위(`mapId`)별로 자산·순찰을 분리**하는 것이다.

---

## 1. Fixed product policies

| # | Policy | Decision |
|---|--------|----------|
| P1 | 재매핑 완료 후 | **새 `mapId`를 만들고 즉시 active** 로 반영한다. |
| P2 | zone / waypoint 편집 | **active 맵만** 가능하다. |
| P3 | 비active 맵 편집 | 그 맵을 **사용 맵(active)으로 지정**한 뒤에만 가능하다. |
| P4 | 과거 맵 파일 | **기본 영구 보관**. 관리자 **삭제 API로만** 제거 가능하다. |
| P5 | active 맵 삭제 | **거부**한다. 삭제 전에 다른 맵을 active로 지정해야 한다. |
| P6 | 구 순찰 데이터 | 완벽 복구는 포기. **이 기능 적용 이후** 순찰부터 `patrol.mapId`로 PDF·상세 UX를 구성한다. |
| P7 | 서버에 이미 있는 맵 | 마이그레이션 시 **삭제하지 않고** 해당 단지의 **최초 active** 로 승격한다. |

---

## 2. Domain model (target)

```text
ApartmentComplex
  └─ activeMapId ──► PatrolMap (status=ACTIVE | ARCHIVED)
                        ├─ files (PNG/YAML metadata) — immutable per mapId
                        ├─ checkpoints/zones (FK map_id)
                        └─ navigation_waypoints (FK map_id, map_version)

Patrol
  └─ mapId (+ mapVersion recommended)  // snapshot at START_PATROL
```

### Invariants

1. 단지당 **active 맵은 정확히 1개** (맵이 0개면 navigation/순찰 시작 불가 — 기존과 동일).
2. 재매핑 업로드는 **기존 row overwrite 금지**. 항상 **INSERT 새 `mapId`**.
3. 이전 active는 **ARCHIVED** 로 전환하고 **파일·zone·waypoint를 지우지 않는다** (삭제 API 제외).
4. `START_PATROL` / robot `navigation-config` 는 **항상 active 맵** 기준.
5. 순찰 상세·PDF·경로 투영은 **`patrol.mapId` 맵** 기준 (active가 아님).
6. `mapId`가 NULL인 구 순찰은 “맵 없음” 또는 최소 폴백 UX (좌표 정합 보장 없음).

---

## 3. As-is vs to-be (backend)

| Area | As-is | To-be |
|------|-------|-------|
| `patrol_maps` | `apartment_complex_id` UNIQUE, 1 row | 단지당 N row, active 1 |
| Map upload | same `mapId` update + file delete + wipe waypoints | INSERT + auto-activate + keep previous |
| Zones/waypoints | scoped by `mapId` but wiped on re-upload | stay on old `mapId`; new empty set on new `mapId` |
| `patrols` | no map FK | `map_id` (+ `map_version`) snapshot |
| `GET /api/map/current` | only map of complex | **active** map |
| Patrol detail `mapUrl` | current complex map | map of `patrol.mapId` |

---

## 4. API contract draft

인증·에러 envelope는 기존 `ApiResponse` / `ErrorCode` 관례를 따른다.  
아래는 **추가·변경 계약**이다. 미기재 필드는 기존 유지.

### 4.1 Map list (new)

`GET /api/map`

- Auth: 단지 관리자  
- Response: 단지 소유 맵 목록 (최신/active 우선 정렬 권장)

```json
{
  "maps": [
    {
      "mapId": 12,
      "mapName": "…",
      "mapUrl": "/api/map/files/…",
      "mapVersion": 1,
      "status": "ACTIVE",
      "createdAt": "2026-08-11T12:00:00",
      "updatedAt": "2026-08-11T12:00:00"
    },
    {
      "mapId": 7,
      "status": "ARCHIVED",
      "mapVersion": 3
    }
  ],
  "activeMapId": 12
}
```

`status`: `ACTIVE` | `ARCHIVED`

### 4.2 Current map (behavior change)

`GET /api/map/current`

- 의미: 단지의 **active** 맵 (필드 형태는 기존 `MapDetailResponse` + `status` 권장)

### 4.3 Map detail (unchanged path, archived OK)

`GET /api/map/{mapId}`

- active/archived 모두 조회 가능 (단지 소유만)
- 삭제된 맵은 404

### 4.4 Activate map (new)

`POST /api/map/{mapId}/activate`  
(또는 `PUT /api/map/active` body `{ "mapId": N }`)

- Auth: 단지 관리자  
- Effect: 해당 맵 ACTIVE, 이전 active → ARCHIVED  
- Idempotent: 이미 active면 성공  
- Reject: 다른 단지 맵, 삭제된 맵  
- After activate: zone/waypoint 편집 대상이 이 `mapId`로 바뀜  
- Robot/FE는 이후 `current` / `navigation-config` 로 새 신원 수신

### 4.5 Delete map (new)

`DELETE /api/map/{mapId}`

- Auth: 단지 관리자  
- Reject if `status=ACTIVE` (먼저 다른 맵 activate)  
- Effect: DB row + 저장 파일 삭제 (해당 맵 zone/waypoint cascade 또는 선행 삭제 — Phase 1에서 FK 전략 확정)  
- 이 맵을 `mapId`로 가진 **과거 순찰**이 있으면:  
  - **권장:** 삭제 거부(참조 중) 또는  
  - **대안:** 순찰은 남기고 `mapUrl`/도면만 비움  
  - Phase 1에서 한 가지로 고정 (기본 제안: **참조 중이면 409**)

### 4.6 Mapping upload (behavior change)

`POST /api/map/mapping-sessions/{mappingSessionId}/map`

기존 응답 필드 유지:

- `mappingSessionId`, `mapId`, `mapUrl`, `mapVersion`, `mappingStatus`, `completedAt`

**Behavior change:**

1. 항상 **새 `mapId`** 발급 (재시도 idempotent는 세션 COMPLETED 시 기존 결과 반환 — 현 패턴 유지).  
2. 새 맵을 **즉시 ACTIVE**.  
3. 이전 active는 ARCHIVED, **파일·경로 데이터 유지**.  
4. 새 맵에는 zone/waypoint **없음** → 관리자가 새 맵에 다시 찍음.  
5. 응답 `mapId` / `mapVersion` 은 IoT·FE가 active 신원으로 사용.

### 4.7 Zones / waypoints (guard change)

기존 경로 유지:

- `GET|PUT /api/map/{mapId}/zones`
- `GET|PUT /api/map/{mapId}/waypoints`

**추가 규칙:**

- `PUT`: path `mapId` 가 **active** 가 아니면 **409** (편집 불가).  
- `GET`: archived 포함 조회 허용 (읽기 전용 확인용).  
- active로 지정(`activate`) 후 동일 API로 편집.

### 4.8 Robot navigation config (behavior change)

`GET /api/robot/navigation-config`

- `schemaVersion: 1` 유지  
- `map.mapId` / `map.mapVersion` = **단지 active 맵**  
- zones / waypoints = 그 맵(+ version) 세트  
- IoT fail-closed `NAVIGATION_MAP_MISMATCH` 와 동일 신원

### 4.9 Patrol start snapshot (domain change)

`START_PATROL` 준비 시:

- active 맵으로 route validation  
- 생성되는 `patrols` row 에 **`map_id` (= active mapId)** 및 **`map_version`** 저장  
- 이후 active가 바뀌어도 해당 순찰의 맵 스냅샷은 불변

### 4.10 Patrol detail / PDF (behavior change)

`PatrolDetailResponse` (및 PDF 입력):

- 추가 권장 필드: `mapId`, `mapVersion` (nullable for legacy)  
- `mapUrl` / resolution·origin 투영: **`patrol.mapId`의 맵**  
- `mapId == null` (레거시): `mapUrl` null 또는 안내 가능한 폴백; **현재 active로 강제 투영하지 않는 것을 기본**으로 한다 (잘못된 겹침 방지).

---

## 5. Migration assumptions (for Phase 1)

1. 기존 `patrol_maps` 1건/단지 → `status=ACTIVE` (또는 `active_map_id` 설정).  
2. `uk_patrol_maps_apartment_complex` 제거.  
3. `patrols.map_id` 컬럼 추가 (NULL 허용 후, 가능하면 유일했던 맵으로 백필).  
4. 이미 파일 overwrite로 사라진 옛 occupancy는 **복구 불가**.  
5. Phase 0 문서만으로는 런타임 변경 없음.

---

## 6. Phase boundaries

| Phase | Deliverable |
|-------|-------------|
| **0 (this doc)** | Policy + API/domain contract freeze |
| **1** | DB migration + entities (no behavior break if possible) |
| **2** | Upload insert-only + auto-activate + list/activate/delete |
| **3** | Active-only edit guards + patrol snapshot + navigation-config |
| **4** | Patrol detail/PDF by `patrol.mapId` |
| **5–6** | FE / IoT against this contract |
| **7** | E2E scenarios |

---

## 7. Open item locked for Phase 1

- **삭제 시 순찰 참조 정책:** 기본안 **409 Conflict (참조 중 삭제 불가)**.  
  제품이 “순찰 유지·도면만 비움”을 원하면 Phase 1 시작 전에 이 문서 §4.5를 개정한다.

---

## 8. Sign-off

- [x] Product policies P1–P7 (chat 2026-08-11)  
- [ ] Backend lead: Phase 1 schema 착수 가능 확인  
- [ ] FE/IoT: §4 계약 리뷰 (구현 착수 전)

Phase 0 완료 기준: 본 문서가 `docs/02-design/features/` 에 존재하고, 위 정책·API가 이후 구현의 단일 기준이 된다.
