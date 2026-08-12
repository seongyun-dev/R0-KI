"""테스트용 인공 지도. ASCII 로 그려서 눈으로 검증할 수 있게 한다.

실제 저장 지도는 크고 느려서 단위 테스트에 쓸 수 없다. 여기 지도들은 각각
**하나의 기하학적 함정**만 담아서, 실패했을 때 원인이 바로 보이게 만들었다.

범례::

    '#'  OCCUPIED   벽
    '.'  FREE       빈 공간
    '?'  UNKNOWN    정답 지도에서도 미지 (벽 바깥. ray 가 여기서 멈춘다)

행은 **위에서 아래로** 적는다 (그림 그리는 순서). 내부적으로 좌하단 원점으로
뒤집으므로, 지도를 보이는 대로 적으면 된다.

해상도 0.05 m 기준 차체는 7 x 5 셀이다. 그래서 "좁은 복도" 는 8~10 셀이어야
간신히 통과하고, 6 셀이면 물리적으로 못 들어간다. 각 지도의 셀 수는 그 사실을
의도적으로 이용한다.
"""

from __future__ import annotations

from typing import Sequence

from .contracts import CellState, GridSpec
from .worldmodel import GroundTruth


_LEGEND = {
    "#": CellState.OCCUPIED,
    ".": CellState.FREE,
    "?": CellState.UNKNOWN,
}


def from_ascii(
    rows: Sequence[str],
    *,
    resolution: float = 0.05,
    origin: tuple[float, float] = (0.0, 0.0),
) -> GroundTruth:
    """ASCII 그림을 정답 지도로. rows[0] 이 지도의 **위쪽**이다."""
    if not rows:
        raise ValueError("빈 지도")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("모든 행의 길이가 같아야 한다")
    height = len(rows)
    spec = GridSpec(
        width=width,
        height=height,
        resolution=resolution,
        origin_x=origin[0],
        origin_y=origin[1],
    )
    cells: list[CellState] = []
    # rows 는 위에서 아래 순서이므로 뒤집어서 좌하단 원점으로 만든다.
    for row in reversed(rows):
        for character in row:
            try:
                cells.append(_LEGEND[character])
            except KeyError as exc:
                raise ValueError(f"알 수 없는 지도 문자 {character!r}") from exc
    return GroundTruth.from_cells(spec, cells)


def _box(width: int, height: int, interior: str = ".") -> list[str]:
    """벽으로 둘러싼 직사각형."""
    top = "#" * width
    middle = "#" + interior * (width - 2) + "#"
    return [top] + [middle] * (height - 2) + [top]


def wide_room() -> GroundTruth:
    """넓은 직사각형 방. 아무 함정이 없다 -- COMPLETE 가 나와야 하는 기준선."""
    return from_ascii(_box(40, 30))


def split_by_wall() -> GroundTruth:
    """벽으로 완전히 분리된 두 공간. 반대편은 영원히 도달 불가.

    올바른 결과는 도달 가능한 쪽을 다 돌고 COMPLETE 다. 반대편 셀은 ray 가
    벽을 뚫지 못하므로 UNKNOWN 으로 남고 프론티어도 생기지 않는다.
    """
    rows = _box(40, 30)
    for index in range(1, 29):
        row = rows[index]
        rows[index] = row[:20] + "#" + row[21:]
    return from_ascii(rows)


def narrow_gap() -> GroundTruth:
    """벽 한가운데 8 셀(0.40 m) 틈. 차체 폭 5 셀이라 통과 가능하지만 여유가 얇다.

    이 지도가 잡는 것: 접근점이 틈 옆 벽에 붙어 선택되면 footprint 가 들어가지
    못해 사전검사가 실패한다. clearance 기반 접근점이면 통과한다.
    """
    rows = _box(40, 30)
    for index in range(1, 29):
        row = rows[index]
        rows[index] = row[:20] + "#" + row[21:]
    # 위에서 12~19 행의 벽을 뚫어 틈을 만든다 (8 셀).
    for index in range(12, 20):
        row = rows[index]
        rows[index] = row[:20] + "." + row[21:]
    return from_ascii(rows)


def u_shape() -> GroundTruth:
    """U 자형. 가운데 블록이 막고 있어 둘러 가야 한다.

    이 지도가 잡는 것: 최소회전반경 0.341 m 로 U 를 돌 수 있는지, 그리고
    "막힌 벽에 계속 부딪히려 한다" 는 실제 증상의 재현.
    """
    rows = _box(44, 32)
    # 가운데 아래쪽에서 위로 뻗은 블록. 좌우로 통로가 남는다.
    for index in range(1, 24):
        row = rows[index]
        rows[index] = row[:16] + "#" * 12 + row[28:]
    return from_ascii(rows)


def narrow_corridor() -> GroundTruth:
    """폭 12 셀(0.60 m) 복도.

    12 셀인 이유: 어떤 자세에서도 안전한 시작점을 두려면 중심에서 벽까지
    circumscribed 0.229 m 이상이 필요하다. 10 셀(0.50 m)이면 중심 여유가
    0.25 m 인데 셀이 사각형이라 실제 근접 거리가 0.225 m 로 떨어져 미달이고,
    그러면 이 지도에서 로봇을 세울 자리가 아예 없다.

    이 지도가 잡는 것: 인플레이션 0.25 vs 0.40 의 차이. 0.40 이면 복도 중앙까지
    인플레이션에 잠겨 cost_penalty 가 경로 선택에 개입한다.
    """
    rows = ["#" * 60 for _ in range(3)]
    rows += ["#" + "." * 58 + "#" for _ in range(12)]
    rows += ["#" * 60 for _ in range(3)]
    return from_ascii(rows)


def dead_end() -> GroundTruth:
    """막다른 길. 끝까지 갔다가 후진하거나 돌아 나와야 한다.

    이 지도가 잡는 것: DUBIN 이면 막다른 길에서 나올 수 없고 (제자리 회전 불가),
    REEDS_SHEPP 이면 후진으로 나올 수 있다. 두 모드의 차이가 여기서 드러난다.
    """
    rows = ["#" * 30 for _ in range(2)]
    rows += ["#" + "." * 28 + "#" for _ in range(12)]
    rows += ["#" * 12 + "." * 10 + "#" * 8 for _ in range(10)]
    rows += ["#" * 30 for _ in range(2)]
    return from_ascii(rows)


def frontier_beside_robot() -> GroundTruth:
    """로봇 바로 옆(0.25 m 이내)에 프론티어가 있는 배치.

    이 지도가 잡는 것: 접근점 후퇴가 parent 체인의 뿌리에 닿는 경우.
    그때 approach == 로봇 셀이 되어 "자기 자리로 가라" 는 목표가 나온다.
    yaw 폴백이 제대로 동작하는지 확인한다.
    """
    rows = ["#" * 26 for _ in range(2)]
    rows += ["#" + "." * 24 + "#" for _ in range(8)]
    # 아래쪽은 주머니 -- 로봇이 여기 서면 바로 옆이 프론티어다. 폭 12 셀로 둔 것은
    # narrow_corridor 와 같은 이유다 (어떤 자세에서도 설 수 있어야 한다).
    rows += ["#" * 8 + "." * 12 + "#" * 6 for _ in range(8)]
    rows += ["#" * 26 for _ in range(2)]
    return from_ascii(rows)


def reopens_after_discovery() -> GroundTruth:
    """처음에는 막힌 것처럼 보이지만 더 탐사하면 우회로가 드러나는 배치.

    이 지도가 잡는 것: 좌표 기반 영구 블랙리스트와 지도 개정 기반 soft blacklist
    의 차이. 왼쪽 방의 프론티어는 초기 관측만으로는 경로가 없어 실패하는데,
    아래쪽 우회 통로를 발견하면 도달 가능해진다. 영구 배제면 영원히 못 가고,
    soft 면 재평가된다.
    """
    rows = _box(48, 34)
    # 중앙 수직벽 -- 위쪽은 막고 아래쪽에만 통로를 남긴다.
    for index in range(1, 27):
        row = rows[index]
        rows[index] = row[:24] + "#" + row[25:]
    return from_ascii(rows)


ALL_MAPS = {
    "wide_room": wide_room,
    "split_by_wall": split_by_wall,
    "narrow_gap": narrow_gap,
    "u_shape": u_shape,
    "narrow_corridor": narrow_corridor,
    "dead_end": dead_end,
    "frontier_beside_robot": frontier_beside_robot,
    "reopens_after_discovery": reopens_after_discovery,
}
