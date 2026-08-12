# 매핑 리플레이 시뮬레이터

실물 로봇 없이 자율 매핑 변경을 **탐사 종료까지 연속으로** 검증하는 오프라인 도구.

기존 검증은 저장 지도 한 시점에서 "프론티어 8개 중 5개 경로 성공" 같은 스냅샷만
봤습니다. 그러면 **한 번 실패한 프론티어가 영구 배제되어 탐사가 죽는 과정**이 보이지
않습니다. 이 도구는 그 과정을 재현합니다.

```
정답 지도 → 초기 관측 → 360° LiDAR ray casting → frontier 검출 → 접근점·목표 yaw
→ 후보별 경로 사전검사 → 최적 후보 선택 → Ackermann 주행 → 지도 갱신 → 반복
→ COMPLETE / STALLED / COLLISION / LOOP / TIMEOUT
```

---

## ⚠️ 무엇이 실측이고 무엇이 근사인가

이 구분이 이 문서에서 가장 중요합니다.

| | 근거 |
|---|---|
| **실측값** — 차체 0.35×0.25 m, 축간거리 0.124 m, 최소회전반경 0.341 m, 속도 0.09 m/s | 줄자 검증 (CLAUDE.md B-7) |
| **실제 설정에서 읽음** — 프론티어 비용식, 재시도·쿨다운 정책, 인플레이션 반경, Smac 페널티, 목표 yaw 규칙 | 해당 태그의 파일을 직접 읽어 구성. `summary.json` 의 `run_metadata.프로필` 에 태그·커밋·출처파일이 기록됩니다 |
| **근사** — 경로계획 | 자체 SE2 격자 탐색입니다. **Nav2 SmacPlannerHybrid 가 아닙니다.** |

### 근사 플래너의 경계

`ApproximateAckermannPlanner` 는 Nav2 와 **같은 비용식**을 씁니다
(`NodeHybrid::getTraversalCost`, 코드에 원문 인용). 같은 것:

- traversal cost 식과 네 페널티 (`reverse` / `change` / `non_straight` / `cost`)
- 상태를 (셀, 각도 bin) 으로 이산화
- 최소회전반경만으로 만든 모션 프리미티브, DUBIN 에는 후진 프리미티브 없음
- 목표 도달 판정이 **정확한 (셀, bin) 일치**이고 `tolerance` 는 폴백이라는 점
- 프리미티브 길이를 "현 ≥ √2·해상도" 로 정하는 규칙 (`MotionTable::initDubin`)

**없는 것:** analytic expansion(Reeds-Shepp 해석해로 목표 직결), 미리 계산한
obstacle/distance 휴리스틱, 경로 스무딩. 그래서 경로 길이가 실제 Nav2 보다 몇 %
길게 나오는 것이 정상입니다.

이 backend 의 목적은 Nav2 경로 길이를 예측하는 것이 **아니고**, 목표 자세가 애초에
도달 가능한지를 프로필 간 같은 규칙으로 판정하는 것입니다.

모든 산출물(화면·`summary.json`·CLI stderr)에 `APPROXIMATE` 가 표시됩니다.
실제 Nav2 결과가 필요하면 ROS 2 환경에서 `--planner-backend nav2` 를 쓰세요
(`ComputePathToPose` 실호출). **자동 폴백은 없습니다** — 근사 결과를 실측으로
표시하지 않기 위해 일부러 그렇게 두었습니다.

---

## 사용법

호스트에 시스템 Python 이 없으므로 프로젝트 venv 를 씁니다.

```bash
C:/workspace/iot/.codex_tmp/iot-ci-venv/Scripts/python.exe robot/tools/mapping_replay_simulator.py --map C:/workspace/iot/artifacts/mapping-review-20260812/map-13-v1-cf6a97edfc6c/map.yaml --profiles v0.2.2,v0.2.5,v0.2.6 --start-x 3.305 --start-y -0.935 --start-yaw-deg 0 --max-steps 400 --output C:/workspace/iot/artifacts/mapping-simulator/run-001
```

시작점이 지도 밖이거나 점유 셀이거나 footprint 가 들어가지 않으면 **실패하고 가능한
FREE 시작점 후보를 출력합니다.** 임의로 다른 곳에서 시작하지 않습니다 — 조용히
옮기면 프로필 비교가 무의미해지기 때문입니다.

주요 옵션:

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--profiles` | `v0.2.2,v0.2.5` | `v0.2.2`, `v0.2.5`, `v0.2.6`, `proposed-clearance`, `upstream-retarget` |
| `--lidar-range` | `8.0` | 최대 거리 [m] |
| `--lidar-angle-step-deg` | `1.0` | 빔 간격 |
| `--lidar-noise` | `0.0` | 거리 노이즈 표준편차. **0 이면 완전 결정론적** |
| `--seed` | `0` | 노이즈 재현용 |
| `--planner-backend` | `approximate` | `nav2` 는 ROS 2 환경 필요 |
| `--replan-on-map-change` | 꺼짐 | 실제 explore 는 `goal_active_` 가드 때문에 목표가 끝날 때까지 재계획하지 않으므로 기본은 꺼짐 |

## 테스트

```bash
cd robot && C:/workspace/iot/.codex_tmp/iot-ci-venv/Scripts/python.exe -m unittest discover -s tools/tests -p "test_mapping*.py"
```

인공 지도 8종(넓은 방 / 벽 분리 / 좁은 틈 / U자 / 좁은 복도 / 막다른 길 /
바로 옆 프론티어 / 재발견 후 접근 가능)에 대해 39개 검사가 돕니다. 핵심 assertion:

- 점유 셀을 통과한 경로는 승인되지 않음
- `allow_unknown=false` 에서 unknown 경로 거부
- DUBIN 후진 0, REEDS_SHEPP 후진 식별
- footprint 충돌 감지 (**자세 의존 충돌** 포함)
- 프론티어가 남은 상태를 COMPLETE 로 표시하지 않음
- map revision 변경 후 soft-block 재평가
- 같은 입력·seed 에서 동일 결과 (**경계 있음**, 아래 참조)

### 결정론의 경계

판정·지표·궤적·후보 목록은 완전히 재현됩니다. **벽시계 필드
(`planning_time_sec`, `compute_time_sec`)는 재현되지 않으며 그래야 정상입니다** —
그 값이 결정에 쓰이면 호스트 속도가 결과를 바꾸므로, 시뮬레이터는 iteration 을
예산으로 쓰고 벽시계는 기록만 합니다. 따라서 `trace.jsonl` 을 바이트로 비교하면
그 필드에서만 차이가 납니다. 실측 확인: 같은 지도·같은 시작점 2회 실행에서 30줄 중
차이 4건, 전부 `planning_time_sec`.

참고로 근사 플래너의 `planning_time_sec` 은 한 계획에서 10 s 를 넘기도 합니다
(Nav2 의 `max_planning_time` 3.5 는 C++ 기준 값입니다). 그래서 이 값을 실패 판정에
쓰지 않습니다. 예산을 소진해 실패한 경우는 `plan_budget_exhausted` 로 따로 셉니다 —
0 이 아니면 그 실행의 계획 실패 수치를 그대로 믿으면 안 됩니다.

---

## 프로필

값은 전부 해당 태그의 파일에서 읽었습니다. 두 태그를 직접 비교한 결과:

```
robot/config/ros/explore.params.yaml         v0.2.2 == v0.2.5  (바이트 동일)
robot/config/ros/nav2.params.yaml.template   planner_server 섹션 차이 없음
robot/src/aiot_robot/ros_config.py           인플레이션 0.25 -> 0.40
                                             mapping 페널티 3개가 명시 핀으로 추가되었으나
                                             수치는 템플릿 기본값과 동일
robot/patches/...frontier-recovery.patch     목표 yaw 규칙 변경 + frontier_free 추가
```

**매핑 동작에 영향을 주는 태그 간 차이는 정확히 두 개입니다:** 목표 yaw 규칙과
인플레이션 반경. 프로필을 그 두 축으로 구성한 것은 임의 선택이 아니라 diff 가
그렇게 나왔기 때문입니다.

| 프로필 | 출처 | 목표 yaw | 인플레이션 | 재시도 |
|---|---|---|---|---|
| `v0.2.2` | `iot-v0.2.2` (341b920) | `atan2(approach − robot)` | 0.25 m | 15 s |
| `v0.2.5` | `iot-v0.2.5` (af1478c) | `atan2(frontier_free − approach)` | 0.40 m | 15 s |
| `v0.2.6` | `iot/feat/v0.2.6-mapping-stability` (8c7a466) **브랜치, 태그 아님** | `atan2(approach − robot)` (v0.2.2 로 회귀) | 0.25 m (회귀) | **5 s** |
| `proposed-clearance` | **릴리스 아님 · 제안** | 기준선 2배 | 0.40 m | 15 s |
| `upstream-retarget` | **태그 아님 · 대조군** | v0.2.5 와 동일 | 0.40 m | 15 s |

`v0.2.6` 은 v0.2.5 의 두 실험(경계 접선 yaw, 인플레이션 0.40)을 **모두 철회**하고
재시도 간격을 줄인 릴리스입니다. 여기에 더해 시뮬레이터로는 표현되지 않는 변경이
있습니다: `progress_timeout` 을 활성 목표에 매기도록 수정, `canceling_goal_` 로 취소
종결을 기다림, `ExploreStatusMonitor` 가 `/explore/status` 를 구독, 매핑 BT 에서
`ClearEntireCostmap` 제거. **clearance 기반 접근점 선택과 `frontier_failures_` 초기화는
v0.2.6 에 없습니다.**

`proposed-clearance` 는 제 진단에서 나온 제안이고 **실제 v0.2.6 브랜치에 없습니다.**
이름에 버전을 붙이지 않은 이유가 그것입니다.

`proposed-clearance` 가 v0.2.5 기준으로 바꾸는 네 가지:

1. 접근점을 clearance 로 고른다 (footprint 가 들어갈 수 있는 첫 셀)
2. 사전검사 실패 시 다른 접근점으로 재시도
3. 실패 병합을 체비셰프 0.25 m 상자 → 유클리드 0.135 m
4. 지도 개정 기반 soft blacklist

**단, 실측 sweep 에서 ②③④ 는 한 번도 발동하지 않았습니다.** 5장 전부에서
`frontier_retries = 0` 이라 `recordGoalFailure` 가 불리지 않았고, 그 셋은 실패가
생겨야 동작하는 코드입니다. 즉 관측된 효과는 **①(clearance 기반 접근점) 하나로
전부 설명됩니다.** ②③④ 는 이 sweep 으로 검증되지 않았으므로 근거 없이 함께
넣지 마세요.

`upstream-retarget` 은 패치가 제거한 upstream 동작(`same_goal && goal_active_`)의
대조군입니다. 패치 주석이 "그 선점을 Humble 이 실제 ABORT 와 구별하지 못해 이전
프론티어의 재시도 예산을 소모한다" 고 주장하는데, 그 손해를 재기 위해 둡니다.

---

## 산출물

한 번 실행하면 `--output` 아래에 네 파일:

| 파일 | 내용 |
|---|---|
| `report.html` | **단일 자체완결 HTML.** 외부 CDN·폰트·스크립트 없음. 재생/일시정지/단계이동/슬라이더 |
| `summary.json` | `run_metadata`(태그·커밋·설정값·출처파일·실측값) + 프로필별 지표 전체 |
| `trace.jsonl` | step 하나가 한 줄. 후보·판정·경로·궤적·지도 개정 |
| `final-map.svg` | 최종 발견 지도 + 궤적 (행 단위 런렝스) |

`report.html` 에 표시되는 것: 현재 발견 지도 / 로봇 pose 와 footprint / 모든
frontier / 후보 색상 구분(승인·거절 사유별) / 선택 목표와 yaw / 계획 경로 / 실제
이동 궤적 / unknown 통과 구간 / 충돌 위치 / cooldown·blacklist 후보 / coverage 와
현재 상태. **정답 지도는 기본 숨김이고 디버그 토글로만 보입니다.**

---

## 종료 상태

`COMPLETE` 와 `STALLED` 를 절대 섞지 않습니다. 실제 시스템이 둘을 구분하지 못해
19% 완성된 지도를 "완료" 로 저장하고 있었고, 그것이 이 도구를 만든 이유입니다.

| 상태 | 의미 |
|---|---|
| `COMPLETE` | **프론티어 셀이 하나도 없음.** 이것만 완주입니다 |
| `WAITING` | 재시도 쿨다운 중 (중간 상태) |
| `STALLED` | 프론티어는 있으나 모든 후보가 실패·제외. 크기 미달만 남은 경우도 여기입니다 |
| `COLLISION` | footprint 가 **정답 지도**의 점유 셀과 충돌 |
| `LOOP` | 동일 (자세, 목표) 조합 반복 |
| `TIMEOUT` | 최대 step 또는 시뮬레이션 시간 초과 |
| `FAILED` | 입력 또는 내부 오류 |

크기 미달 프론티어만 남은 상태를 `COMPLETE` 로 부르지 않는 것이 의도적입니다.
`min_frontier_size: 0.35` 가 실제 개구부를 버리는 문제를 드러내기 위해서입니다.

---

## 한계 — 이 도구가 증명하지 못하는 것

1. **경로 품질은 Nav2 와 다릅니다.** analytic expansion·스무딩·사전계산 휴리스틱이
   없습니다. 길이·확장수를 Nav2 수치로 인용하지 마세요.
2. **SLAM 을 모사하지 않습니다.** 지도는 정답 지도에서 ray casting 으로 공개되며,
   루프클로저·드리프트·자세 추정 오차가 없습니다. rf2o 드리프트나 스캔매칭 실패로
   생기는 문제는 여기서 재현되지 않습니다.
3. **컨트롤러가 없습니다.** 계획 경로를 그대로 따라갑니다. RPP 의 추종 오차,
   `yaw_goal_tolerance` 미달로 인한 goal checker 실패, 속도 스무딩, PWM 하한
   (38 이하 좌우 편차, 36 이하 stall) 은 모델에 없습니다.
4. **장애물이 정적입니다.** 사람·움직이는 물체가 없습니다.
5. **한 프로필당 한 번의 실행입니다.** 결정론적이라 반복해도 같은 결과이며,
   따라서 "반복 가능성"(합격 기준의 핵심)을 이 도구로는 증명할 수 없습니다.
6. **v0.2.6 의 실제 변경 대부분을 평가할 수 없습니다.** 아래를 보세요.

### ⚠️ v0.2.6 을 이 도구로 평가할 때의 함정

실측 결과 **v0.2.6 의 커버리지·이동거리가 5장 전부에서 v0.2.2 와 완전히 같습니다.**
그것을 "v0.2.6 이 v0.2.2 와 동등하다" 는 증거로 읽으면 **틀립니다.** v0.2.6 의 변경
대부분이 이 모델에 없어서 같게 나오는 것입니다:

| v0.2.6 의 변경 | 모델링 여부 | 이유 |
|---|---|---|
| 인플레이션 0.40 → 0.25 | ✅ | v0.2.2 와 같은 값이 되어 차이가 사라짐 |
| 목표 yaw v0.2.2 로 회귀 | ✅ | v0.2.2 와 같은 규칙이 되어 차이가 사라짐 |
| `frontier_retry_delay` 15 → 5 | ✅ | 유일하게 남는 차이 |
| `progress_timeout` 을 활성 목표에 매김 | ❌ | 컨트롤러가 없어 `progress_timeout` 자체가 발화하지 않음 |
| `canceling_goal_` 취소 종결 대기 | ❌ | `retarget_while_active=False` 라 취소 경로를 타지 않음 |
| `/explore/status` 구독 + stall 생애주기 | ❌ | 오케스트레이션 레이어는 모델 밖 |
| BT 에서 `ClearEntireCostmap` 제거 | ❌ | BT 를 모델링하지 않음 |

`ModelCoverageTest` 가 이 사실을 테스트로 고정합니다. 침묵을 증거로 오해하지 않기
위한 것이고, `simulator.py` 가 `progress_timeout_sec` 을 쓰기 시작하면 그 테스트가
실패해 목록을 갱신하도록 만들어 두었습니다.

**결론적으로 이 도구는 "논리 검증" 입니다.** 여기서 통과한 변경도 실물에서
반드시 다시 확인해야 합니다. 여기서 실패한 변경은 실물에서도 실패할 가능성이
높지만, 그 역은 성립하지 않습니다.

## 안전

- 운영 코드를 수정하지 않습니다. `robot/tools/` 아래 신규 파일만 추가합니다
- MQTT·ESP32·시리얼·ROS 노드를 열지 않습니다 (`--planner-backend nav2` 예외)
- `import` 만으로 아무 일도 일어나지 않습니다
- 표준 라이브러리만 씁니다. 유일한 외부 의존성은 `robot/roki/navigation/map_metadata.py`
  가 이미 쓰는 PyYAML 입니다 (지도 로더를 재구현하지 않고 재사용)
