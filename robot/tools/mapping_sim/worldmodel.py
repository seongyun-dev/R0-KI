"""정답 지도(GroundTruth)와 발견 지도(DiscoveredMap).

이 모듈이 지키는 불변식은 하나다: **탐사 알고리즘은 미래를 볼 수 없다.**

그래서 두 지도를 서로 대체 불가능한 별개 공개 타입으로 두었다. raycast 와
실제 충돌 판정은 ``GroundTruth`` 에만 있고, 프론티어 검출·경로계획·목표선택이
필요로 하는 조회는 ``DiscoveredMap`` 에만 있다. 시그니처가 곧 검사기라서,
플래너에 정답 지도를 넘기는 코드는 타입 이름만 보고도 리뷰에서 잡힌다.
(두 지도가 공유하는 것은 격자 저장과 기하 계산뿐이고 그것만 ``_GridBody``
에 있다. 상속은 구현 재사용 용도이며 다형성으로 쓰지 않는다.)

근사와 실측의 구분: 여기 있는 비용 계산은 Nav2 InflationLayer 를 재현하려는
근사다. 특히 Nav2 는 셀 중심 사이 거리를 쓰지만 우리는 셀 사각형까지의 거리를
쓴다 -- 벽 여유를 과대평가하지 않으려고 일부러 보수적으로 잡았다.
"""

from __future__ import annotations

import importlib
import math
import random
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable, Sequence

from .contracts import (
    COST_LETHAL,
    COST_UNKNOWN,
    CellState,
    GridSpec,
    InflationSpec,
    LidarSpec,
    Pose,
    RobotSpec,
    polygon_overlaps_cell,
)

__all__ = ["DiscoveredMap", "GroundTruth"]


# 격자는 CellState 객체가 아니라 그 value(int) 로 저장한다. raycast 내부 루프가
# 한 step 에 수만 번 돌기 때문에 Enum 비교 오버헤드를 감당할 수 없다. 공개 API
# 경계에서만 CellState 로 되돌린다.
_UNKNOWN = CellState.UNKNOWN.value
_FREE = CellState.FREE.value
_OCCUPIED = CellState.OCCUPIED.value

_STATE_OF_VALUE: dict[int, CellState] = {
    _UNKNOWN: CellState.UNKNOWN,
    _FREE: CellState.FREE,
    _OCCUPIED: CellState.OCCUPIED,
}

# 점유셀 공간 버킷 한 변의 셀 수. 0.05 m 격자에서 0.40 m 상자가 되고, 실제
# 질의 반경(circumscribed 0.229, inflation 0.25~0.40)이 버킷 한두 겹 안에
# 들어온다. 더 작게 잡으면 링 순회 횟수가, 더 크게 잡으면 버킷 내 선형탐색이
# 늘어난다.
_BUCKET_CELLS = 8

# footprint 충돌에서 막는 셀 종류. 프로필의 allow_unknown 을 이 두 집합의
# 선택으로 표현한다.
_BLOCKED_OCCUPIED: frozenset[int] = frozenset((_OCCUPIED,))
_BLOCKED_OCCUPIED_OR_UNKNOWN: frozenset[int] = frozenset((_OCCUPIED, _UNKNOWN))

# 지연 로드된 navigation.map_metadata. 모듈 최상위에서 import 하면 sys.path 를
# 건드리는 부작용이 생기므로 첫 사용 시점까지 미룬다.
_MAP_METADATA_MODULE: ModuleType | None = None


def _load_map_metadata_module() -> ModuleType:
    """운영 지도 로더를 지연 import 한다.

    PGM 파서를 다시 쓰지 않는 이유: P2/P5, negate, occupied_thresh/free_thresh,
    canonical unknown(205) 처리를 운영 코드가 이미 하고 있고, 시뮬레이터가 별도
    파서를 갖는 순간 "시뮬레이터에서만 통하는 지도" 가 생긴다.

    ``navigation`` 패키지가 절대 import(``from navigation.route import ...``)를
    쓰므로 ``robot/roki`` 를 sys.path 에 넣어야 한다. 그 부작용을 import 시점이
    아니라 이 함수 안으로 밀어 넣었다.
    """
    global _MAP_METADATA_MODULE
    if _MAP_METADATA_MODULE is not None:
        return _MAP_METADATA_MODULE
    roki_root = Path(__file__).resolve().parents[2] / "roki"
    if not (roki_root / "navigation" / "map_metadata.py").is_file():
        raise FileNotFoundError(
            f"지도 로더를 찾을 수 없다: {roki_root / 'navigation' / 'map_metadata.py'}"
        )
    root = str(roki_root)
    if root not in sys.path:
        # append 다. insert(0) 로 넣으면 robot/roki 아래의 흔한 이름들
        # (config, state, common, runtime, tests) 이 top-level 이름 경쟁에서
        # 이기고, 특히 `tests` 가 G4 회귀 테스트 수집을 가로챈다.
        sys.path.append(root)
    _MAP_METADATA_MODULE = importlib.import_module("navigation.map_metadata")
    return _MAP_METADATA_MODULE


def _ring_keys(base_col: int, base_row: int, ring: int) -> Iterable[tuple[int, int]]:
    """버킷 좌표계에서 체비셰프 거리 ``ring`` 인 버킷 키들."""
    if ring == 0:
        yield (base_col, base_row)
        return
    for offset in range(-ring, ring + 1):
        yield (base_col + offset, base_row + ring)
        yield (base_col + offset, base_row - ring)
    for offset in range(-ring + 1, ring):
        yield (base_col - ring, base_row + offset)
        yield (base_col + ring, base_row + offset)


class _GridBody:
    """두 지도가 공유하는 격자 저장소와 기하 연산. 공개 타입이 아니다."""

    spec: GridSpec

    def __init__(self, spec: GridSpec, cell_values: Sequence[int]) -> None:
        """정상 생성 경로는 각 공개 클래스의 생성자/클래스메서드다.

        ``cell_values`` 는 좌하단 원점 행 우선(row-major, row 0 = 최하단)이고
        값은 CellState.value 여야 한다.
        """
        expected = spec.width * spec.height
        if len(cell_values) != expected:
            raise ValueError(
                f"셀 개수가 {expected} 이어야 한다 (받은 값 {len(cell_values)})"
            )
        self.spec = spec
        self._cells: list[int] = list(cell_values)
        self._free_count = 0
        self._known_count = 0
        self._occupied: list[tuple[int, int]] = []
        self._buckets: dict[tuple[int, int], list[tuple[int, int]]] = {}
        width = spec.width
        for index, value in enumerate(self._cells):
            if value == _FREE:
                self._free_count += 1
                self._known_count += 1
            elif value == _OCCUPIED:
                self._known_count += 1
                self._register_occupied(index % width, index // width)
            elif value != _UNKNOWN:
                raise ValueError(f"셀 값 {value!r} 은 CellState 가 아니다")

    # -- 내부 인덱스 -------------------------------------------------------

    def _register_occupied(self, col: int, row: int) -> None:
        self._occupied.append((col, row))
        key = (col // _BUCKET_CELLS, row // _BUCKET_CELLS)
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = [(col, row)]
        else:
            bucket.append((col, row))

    # -- 조회 --------------------------------------------------------------

    def flat_states(self) -> list[int]:
        """``GridSpec.index`` 순서(row 0 = 아래쪽, index = row*width+col)의 셀 값.

        사본을 준다. 리포트가 이 리스트를 제자리에서 고치면 지도가 조용히 바뀌고
        그 뒤의 충돌 판정과 raycast 가 전부 거짓이 되기 때문이다.
        """
        return list(self._cells)

    def _state(self, col: int, row: int) -> CellState:
        spec = self.spec
        # 지도 밖은 UNKNOWN 으로 답한다. 플래너가 경계마다 방어코드를 두지 않아도
        # 되게 하려는 것이고, 안전은 _footprint_blocked 가 지도 밖을 충돌로
        # 판정해서 지킨다 (조회는 관대하게, 판정은 엄격하게).
        if not (0 <= col < spec.width and 0 <= row < spec.height):
            return CellState.UNKNOWN
        return _STATE_OF_VALUE[self._cells[row * spec.width + col]]

    def _min_obstacle_distance(self, x: float, y: float, limit_m: float) -> float:
        """(x, y) 에서 가장 가까운 점유셀 **사각형** 까지의 거리.

        셀 중심까지의 거리가 아니다. 이 값으로 벽 여유를 재기 때문에, 중심을
        쓰면 최대 0.035 m(대각 반셀)까지 여유를 과대평가한다.

        ``limit_m`` 안에 점유셀이 없으면 ``limit_m`` 을 그대로 돌려준다.
        전수 탐색 대신 버킷 링을 안에서 밖으로 훑고 조기 종료한다.
        """
        if limit_m <= 0.0 or not self._buckets:
            return limit_m
        spec = self.spec
        res = spec.resolution
        origin_x = spec.origin_x
        origin_y = spec.origin_y
        bucket_m = _BUCKET_CELLS * res
        limit_sq = limit_m * limit_m
        best_sq = limit_sq
        base_col = math.floor((x - origin_x) / res) // _BUCKET_CELLS
        base_row = math.floor((y - origin_y) / res) // _BUCKET_CELLS
        buckets = self._buckets
        max_ring = int(math.ceil(limit_m / bucket_m)) + 1
        for ring in range(max_ring + 1):
            if ring:
                # 체비셰프 ring 번째 버킷의 셀은 점에서 최소 (ring-1)*bucket_m
                # 떨어져 있다 (사이에 버킷 ring-1 겹이 온전히 들어간다).
                # 이미 그보다 가까운 답을 얻었으면 남은 링은 볼 필요가 없다.
                bound = (ring - 1) * bucket_m
                if best_sq <= bound * bound:
                    break
            for key in _ring_keys(base_col, base_row, ring):
                cells = buckets.get(key)
                if not cells:
                    continue
                for col, row in cells:
                    cell_x = origin_x + col * res
                    dx = cell_x - x
                    if dx < 0.0:
                        dx = x - (cell_x + res)
                        if dx < 0.0:
                            dx = 0.0          # x 가 셀 폭 안에 있다
                    cell_y = origin_y + row * res
                    dy = cell_y - y
                    if dy < 0.0:
                        dy = y - (cell_y + res)
                        if dy < 0.0:
                            dy = 0.0
                    distance_sq = dx * dx + dy * dy
                    if distance_sq < best_sq:
                        best_sq = distance_sq
        if best_sq >= limit_sq:
            return limit_m
        return math.sqrt(best_sq)

    def _footprint_blocked(
        self, pose: Pose, robot: RobotSpec, blocked: frozenset[int]
    ) -> bool:
        spec = self.spec
        res = spec.resolution
        origin_x = spec.origin_x
        origin_y = spec.origin_y
        corners = robot.footprint_corners(pose)
        min_x = min(px for px, _ in corners)
        max_x = max(px for px, _ in corners)
        min_y = min(py for _, py in corners)
        max_y = max(py for _, py in corners)
        # 지도 밖으로 나가는 footprint 는 충돌로 취급한다. 볼록다각형은 AABB 가
        # 지도 사각형 안일 때만 지도 안이므로 이 검사만으로 정확하다.
        if (
            min_x < origin_x
            or min_y < origin_y
            or max_x > origin_x + spec.width * res
            or max_y > origin_y + spec.height * res
        ):
            return True
        # 후보 셀은 실제 꼭짓점 AABB 로 좁힌다 (circumscribed 상자보다 항상
        # 좁으면서 절대 놓치지 않는다). 그 뒤 SAT 로 정확히 본다 -- 셀 중심
        # 샘플링은 한 칸 두께 벽을 통과시킨다.
        col_lo = max(0, math.floor((min_x - origin_x) / res))
        col_hi = min(spec.width - 1, math.floor((max_x - origin_x) / res))
        row_lo = max(0, math.floor((min_y - origin_y) / res))
        row_hi = min(spec.height - 1, math.floor((max_y - origin_y) / res))
        cells = self._cells
        width = spec.width
        for row in range(row_lo, row_hi + 1):
            base = row * width
            cell_min_y = origin_y + row * res
            for col in range(col_lo, col_hi + 1):
                if cells[base + col] not in blocked:
                    continue
                if polygon_overlaps_cell(
                    corners, origin_x + col * res, cell_min_y, res
                ):
                    return True
        return False


class GroundTruth(_GridBody):
    """정답 지도. raycast 와 실제 충돌 판정 전용.

    프론티어 검출·경로계획·목표선택 함수는 이 타입을 인자로 받지 않는다.
    """

    @classmethod
    def from_map_yaml(cls, path: str | Path) -> "GroundTruth":
        """Nav2 map YAML + PGM 을 정답 지도로 읽는다."""
        module = _load_map_metadata_module()
        metadata = module.load_map_metadata(path)
        if abs(metadata.origin_yaw_rad) > 1e-9:
            # GridSpec 은 축정렬 격자만 표현한다. 회전 origin 을 조용히 무시하면
            # 모든 좌표가 어긋나므로 여기서 끊는다.
            raise ValueError(
                "회전된 map origin(yaw="
                f"{metadata.origin_yaw_rad:.6f})은 지원하지 않는다"
            )
        grid = module.load_occupancy_grid(metadata)
        width = metadata.width_px
        height = metadata.height_px
        spec = GridSpec(
            width=width,
            height=height,
            resolution=metadata.resolution_m,
            origin_x=metadata.origin_x,
            origin_y=metadata.origin_y,
        )
        # OccupancyGrid.cells 는 **이미지 행 우선**(첫 행이 지도 최상단)이고
        # GridSpec 은 **좌하단 원점**이다. 행 단위 슬라이스로 위아래를 뒤집는다
        # (셀 단위 루프보다 5만 셀에서 눈에 띄게 빠르다). 값 -1/0/100 은
        # CellState.value 와 같아서 값 변환은 필요 없다.
        source = grid.cells
        values: list[int] = []
        for row in range(height):
            start = (height - 1 - row) * width
            values.extend(source[start : start + width])
        return cls(spec, values)

    @classmethod
    def from_cells(cls, spec: GridSpec, cells: Sequence[CellState]) -> "GroundTruth":
        """테스트용 합성 지도. ``cells`` 는 좌하단 원점 행 우선."""
        return cls(spec, [CellState(cell).value for cell in cells])

    # -- 조회 --------------------------------------------------------------

    def state_at_cell(self, col: int, row: int) -> CellState:
        return self._state(col, row)

    def state_at_world(self, x: float, y: float) -> CellState:
        col, row = self.spec.world_to_cell(x, y)
        return self._state(col, row)

    def free_cell_count(self) -> int:
        return self._free_count

    def min_obstacle_distance(self, x: float, y: float, limit_m: float) -> float:
        return self._min_obstacle_distance(x, y, limit_m)

    def footprint_collides(self, pose: Pose, robot: RobotSpec) -> bool:
        """실제 충돌. 점유셀과 지도 경계만 본다.

        정답 지도의 UNKNOWN 은 "벽 바깥"이고 벽을 통과하지 않으면 닿을 수 없다.
        그래서 UNKNOWN 을 충돌로 세지 않는다 -- 그렇게 세면 벽 바로 뒤 UNKNOWN
        때문에 정상 주행이 충돌로 기록된다.
        """
        return self._footprint_blocked(pose, robot, _BLOCKED_OCCUPIED)

    # -- 관측 --------------------------------------------------------------

    def raycast(
        self,
        pose: Pose,
        lidar: LidarSpec,
        rng: random.Random | None = None,
    ) -> list[tuple[int, int, CellState]]:
        """360도 스캔 한 번이 공개하는 셀 목록. 중복이 있을 수 있다.

        각 빔은 지나간 셀을 FREE 로, 처음 만난 점유셀을 OCCUPIED 로 공개하고
        멈춘다. 격자 순회는 Amanatides-Woo DDA 라서 셀을 건너뛰지 않는다 --
        한 칸 두께 벽을 통과하면 시뮬레이션 결론이 통째로 거짓이 된다.

        ``rng`` 가 None 이거나 ``range_noise_m`` 이 0 이면 rng 를 한 번도 호출하지
        않는다 (완전 결정론).

        알려진 보수적 근사: ``min_range_m`` 데드존 안은 공개하지 않으므로 시작
        자세 주변 반경 0.2 m 가 UNKNOWN 으로 남는다. 실제 slam_toolbox 는 유효
        빔의 **원점부터** 자유공간을 새기므로 이 부분은 실물보다 비관적이다.
        """
        spec = self.spec
        res = spec.resolution
        origin_x = spec.origin_x
        origin_y = spec.origin_y
        width = spec.width
        height = spec.height
        cells = self._cells
        start_col = math.floor((pose.x - origin_x) / res)
        start_row = math.floor((pose.y - origin_y) / res)
        if not (0 <= start_col < width and 0 <= start_row < height):
            return []          # 지도 밖의 자세에서는 관측할 것이 없다
        max_range = lidar.max_range_m
        min_range = lidar.min_range_m
        increment = math.radians(lidar.angle_increment_deg)
        # rng 가 없으면 노이즈 파라미터가 있어도 결정론을 유지한다.
        noise_sigma = lidar.range_noise_m if rng is not None else 0.0
        revealed: list[tuple[int, int, CellState]] = []
        free_state = CellState.FREE
        occupied_state = CellState.OCCUPIED
        for beam in range(lidar.beam_count):
            angle = pose.yaw + beam * increment
            dir_x = math.cos(angle)
            dir_y = math.sin(angle)
            col = start_col
            row = start_row
            if dir_x > 0.0:
                step_col = 1
                t_next_x = (origin_x + (col + 1) * res - pose.x) / dir_x
                t_delta_x = res / dir_x
            elif dir_x < 0.0:
                step_col = -1
                t_next_x = (origin_x + col * res - pose.x) / dir_x
                t_delta_x = -res / dir_x
            else:
                step_col = 0
                t_next_x = math.inf
                t_delta_x = math.inf
            if dir_y > 0.0:
                step_row = 1
                t_next_y = (origin_y + (row + 1) * res - pose.y) / dir_y
                t_delta_y = res / dir_y
            elif dir_y < 0.0:
                step_row = -1
                t_next_y = (origin_y + row * res - pose.y) / dir_y
                t_delta_y = -res / dir_y
            else:
                step_row = 0
                t_next_y = math.inf
                t_delta_y = math.inf
            t_entry = 0.0
            hit_col = -1
            hit_row = -1
            hit_distance = 0.0
            # (col, row, 진입거리). 진입거리는 노이즈가 끝점을 앞으로 당길 때
            # 뒤쪽 FREE 를 잘라내려고 들고 있는다.
            pending: list[tuple[int, int, float]] = []
            while t_entry < max_range:
                t_exit = t_next_x if t_next_x < t_next_y else t_next_y
                value = cells[row * width + col]
                if value == _OCCUPIED:
                    if t_exit > min_range:
                        hit_col = col
                        hit_row = row
                        hit_distance = t_entry
                    # 데드존 안의 벽은 실물 라이다도 값을 못 준다. 그때는
                    # 아무것도 공개하지 않고 빔을 끝낸다 (차폐는 그대로 성립).
                    break
                if value == _UNKNOWN:
                    # 정답 지도의 UNKNOWN 은 벽 바깥이라 관측 대상이 아니다.
                    # 이 셀은 공개하지 않고 빔을 끝낸다. 앞서 지나온 FREE 는
                    # 실제로 보인 것이므로 남긴다.
                    break
                if t_exit > min_range:
                    pending.append((col, row, t_entry))
                if t_next_x <= t_next_y:
                    # 정확히 같을 때(격자 모서리 통과) x 만 진행시킨다. 두 축을
                    # 동시에 넘기면 모서리에서 대각으로 셀을 건너뛰어 얇은 벽을
                    # 통과한다. 한 축씩 가면 셀 하나를 더 보긴 하지만 새지 않는다.
                    col += step_col
                    t_entry = t_next_x
                    t_next_x += t_delta_x
                else:
                    row += step_row
                    t_entry = t_next_y
                    t_next_y += t_delta_y
                if not (0 <= col < width and 0 <= row < height):
                    break
            reported = max_range
            if hit_col >= 0:
                reported = hit_distance
                if noise_sigma > 0.0 and rng is not None:
                    # 노이즈는 "측정된 거리" 에만 준다. 최대거리로 끝난 빔은
                    # 측정값이 없으므로 흔들 대상이 아니다.
                    reported = hit_distance + rng.gauss(0.0, noise_sigma)
                    if reported < min_range:
                        reported = min_range
                    elif reported > max_range:
                        reported = max_range
                    noisy_col = math.floor(
                        (pose.x + reported * dir_x - origin_x) / res
                    )
                    noisy_row = math.floor(
                        (pose.y + reported * dir_y - origin_y) / res
                    )
                    if 0 <= noisy_col < width and 0 <= noisy_row < height:
                        hit_col = noisy_col
                        hit_row = noisy_row
            for cell_col, cell_row, entry in pending:
                if entry < reported:
                    revealed.append((cell_col, cell_row, free_state))
            if hit_col >= 0:
                # FREE 뒤에 붙인다. 같은 셀이 양쪽에 들어가도 DiscoveredMap 이
                # 점유를 고착시키므로 결과는 순서와 무관하게 OCCUPIED 다.
                revealed.append((hit_col, hit_row, occupied_state))
        return revealed

    # -- 진단 --------------------------------------------------------------

    def free_start_candidates(
        self, robot: RobotSpec, limit: int = 12
    ) -> list[tuple[float, float]]:
        """어떤 yaw 에서도 안전한 FREE 셀 중심들. 지도 중앙에 가까운 순.

        자세를 모른 채 줄 수 있는 유일한 보증이 "footprint 외접원이 비어 있다"
        이므로 circumscribed 기준으로 고른다 (inscribed 로 고르면 특정 yaw 에서
        충돌하는 지점을 추천하게 된다 -- 2026-08-12 실측에서 목표 (1.373,0.137)
        이 정확히 그 경우였다).

        가까운 순으로 먼저 정렬한 뒤 필요한 개수만 검사한다. 5만 셀 전부에
        여유 계산을 돌리지 않으려는 것이다.
        """
        if limit <= 0:
            return []
        spec = self.spec
        res = spec.resolution
        radius = robot.circumscribed_radius_m
        # 반경과 정확히 같은 거리에서 '못 찾음'이 나오게 한 셀 여유를 준다.
        probe_limit = radius + res
        center_x = spec.origin_x + spec.width * res / 2.0
        center_y = spec.origin_y + spec.height * res / 2.0
        width = spec.width
        ranked: list[tuple[float, float, float]] = []
        for index, value in enumerate(self._cells):
            if value != _FREE:
                continue
            col = index % width
            row = index // width
            x = spec.origin_x + (col + 0.5) * res
            y = spec.origin_y + (row + 0.5) * res
            ranked.append(((x - center_x) ** 2 + (y - center_y) ** 2, x, y))
        ranked.sort()
        edge_min_x = spec.origin_x + radius
        edge_max_x = spec.origin_x + spec.width * res - radius
        edge_min_y = spec.origin_y + radius
        edge_max_y = spec.origin_y + spec.height * res - radius
        chosen: list[tuple[float, float]] = []
        for _, x, y in ranked:
            # 지도 밖으로 나가는 footprint 도 충돌이다. min_obstacle_distance 는
            # 점유셀만 재는 값이라 경계를 모르므로 여기서 따로 본다.
            if not (edge_min_x <= x <= edge_max_x and edge_min_y <= y <= edge_max_y):
                continue
            if self._min_obstacle_distance(x, y, probe_limit) < radius:
                continue
            chosen.append((x, y))
            if len(chosen) >= limit:
                break
        return chosen


class DiscoveredMap(_GridBody):
    """탐사가 지금까지 발견한 지도. 플래너와 프론티어 검출이 보는 유일한 지도.

    ``revision`` 은 "무언가 새로 발견됐다" 는 사건 카운터다. 재평가
    (``BlacklistMode.MAP_REVISION_SOFT``) 와 비용 캐시 무효화가 이 값을 본다.
    """

    revision: int

    def __init__(self, spec: GridSpec) -> None:
        super().__init__(spec, [_UNKNOWN] * (spec.width * spec.height))
        self.revision = 0
        self._cost_cache: dict[tuple[int, int, int, InflationSpec, float], int] = {}
        self._cost_cache_revision = 0
        # 셀이 처음 알려진 시점의 step. -1 은 아직 미지.
        #
        # reveal 이 어차피 UNKNOWN -> 무엇 전이를 감지하고 있으므로 여기서 함께
        # 기록하면 추가 비용이 없다. 사후에 전체 격자를 다시 훑어 계산하려면
        # 관측 횟수 x 셀 수가 되어 (29,315 셀 x 수천 회) 감당이 안 된다.
        self._first_seen_step: list[int] = [-1] * (spec.width * spec.height)
        self._current_step = 0

    # -- 갱신 --------------------------------------------------------------

    def mark_step(self, step: int) -> None:
        """이후 공개되는 셀에 기록할 step 번호. 리포트 재생용이다."""
        self._current_step = step

    def first_seen_steps(self) -> list[int]:
        """``GridSpec.index`` 순서의 최초 관측 step. 미지 셀은 -1."""
        return list(self._first_seen_step)

    def reveal(self, cells: Iterable[tuple[int, int, CellState]]) -> bool:
        """관측 결과를 반영하고 무언가 바뀌었으면 True.

        규칙 두 가지, 둘 다 의도적이다.

        1. UNKNOWN 공개는 무시한다. 관측은 정보를 늘리기만 하며, 지웠다 다시
           채우면 프론티어가 진동한다.
        2. 점유는 고착시킨다(OCCUPIED -> FREE 강등 없음). 노이즈 한 방으로 벽이
           지워지면 플래너가 벽을 통과하는 경로를 내고, 이 시뮬레이터가 내놓는
           비교 결론이 통째로 거짓이 된다. FREE -> OCCUPIED 승격은 허용한다
           (빔이 그 셀에서 끝났다는 것은 강한 증거다).
        """
        spec = self.spec
        width = spec.width
        height = spec.height
        grid = self._cells
        changed = False
        for col, row, state in cells:
            if not (0 <= col < width and 0 <= row < height):
                continue
            value = state.value
            if value == _UNKNOWN:
                continue
            index = row * width + col
            current = grid[index]
            if current == value or current == _OCCUPIED:
                continue
            if current == _UNKNOWN:
                self._known_count += 1
                self._first_seen_step[index] = self._current_step
            else:
                self._free_count -= 1
            grid[index] = value
            if value == _FREE:
                self._free_count += 1
            else:
                self._register_occupied(col, row)
            changed = True
        if changed:
            self.revision += 1
        return changed

    # -- 조회 --------------------------------------------------------------

    def state_at_cell(self, col: int, row: int) -> CellState:
        return self._state(col, row)

    def state_at_world(self, x: float, y: float) -> CellState:
        col, row = self.spec.world_to_cell(x, y)
        return self._state(col, row)

    def known_cell_count(self) -> int:
        return self._known_count

    def free_cell_count(self) -> int:
        return self._free_count

    def occupied_cells(self) -> list[tuple[int, int]]:
        # 사본을 준다. 프론티어 검출이 받은 목록을 정렬해도 인덱스가 깨지면
        # 안 된다.
        return list(self._occupied)

    def min_obstacle_distance(self, x: float, y: float, limit_m: float) -> float:
        return self._min_obstacle_distance(x, y, limit_m)

    def footprint_collides(
        self, pose: Pose, robot: RobotSpec, *, unknown_is_obstacle: bool
    ) -> bool:
        """발견 지도 기준 충돌. UNKNOWN 취급을 호출자가 정한다.

        ``unknown_is_obstacle`` 이 프로필의 ``allow_unknown`` 을 뒤집은 값이다.
        키워드 전용으로 둔 것은 두 정책이 결과를 크게 바꾸기 때문에 호출부에서
        어느 쪽인지 읽히게 하려는 것이다.
        """
        blocked = (
            _BLOCKED_OCCUPIED_OR_UNKNOWN if unknown_is_obstacle else _BLOCKED_OCCUPIED
        )
        return self._footprint_blocked(pose, robot, blocked)

    def inflation_cost_at_world(
        self, x: float, y: float, inflation: InflationSpec, robot: RobotSpec
    ) -> int:
        """Nav2 InflationLayer 재현 비용. 셀 단위 값이다.

        거리를 **셀 중심** 에서 재는 이유: Nav2 의 비용은 셀당 하나이고, 그래야
        셀 단위 캐시가 근사가 아니라 정확한 재사용이 된다. (Nav2 는 셀 중심
        사이 거리를 쓰지만 우리는 셀 사각형까지의 거리를 쓴다 -- 반 셀만큼
        보수적, 즉 비용을 낮게 잡지 않는다.)
        """
        spec = self.spec
        col, row = spec.world_to_cell(x, y)
        if not spec.contains(col, row):
            # 지도 밖은 통행 불가다. 경로가 지도를 벗어나면 안 된다.
            return COST_LETHAL
        if self.revision != self._cost_cache_revision:
            # 개정이 바뀌면 통째로 버린다. 키에 개정을 넣어도 무효 항목을 남기면
            # (셀 수 x 개정 수) 만큼 메모리가 자란다.
            self._cost_cache.clear()
            self._cost_cache_revision = self.revision
        inscribed = robot.inscribed_radius_m
        key = (self.revision, col, row, inflation, inscribed)
        cached = self._cost_cache.get(key)
        if cached is not None:
            return cached
        value = self._cells[row * spec.width + col]
        if value == _OCCUPIED:
            cost = COST_LETHAL
        elif value == _UNKNOWN:
            cost = COST_UNKNOWN
        else:
            cell_x, cell_y = spec.cell_to_world(col, row)
            # inflation_radius 와 정확히 같은 거리에서 COST_FREE 가 나오도록 한
            # 셀 더 멀리까지 잰다. cost_at_distance 는 distance > radius 일 때만
            # COST_FREE 를 주기 때문이다.
            distance = self._min_obstacle_distance(
                cell_x, cell_y, inflation.inflation_radius_m + spec.resolution
            )
            cost = inflation.cost_at_distance(distance, inscribed)
        self._cost_cache[key] = cost
        return cost
