"""
Serial 문자열에서 완성된 JSON 객체를 추출한다.

Serial 데이터는 항상 한 번의 read 호출로
정확히 하나의 JSON이 들어온다고 보장할 수 없다.

가능한 입력 예:

1. 하나의 정상 JSON
   {"type":"hardwareStatus",...}

2. 두 번에 나뉜 JSON
   {"type":"hardware
   Status",...}

3. 여러 JSON이 한 번에 수신
   {...}{...}

4. ESP32 재부팅 로그와 JSON이 함께 수신
   boot message...
   {...}

이 클래스는 중괄호의 시작과 끝을 기준으로
완성된 JSON 문자열만 반환한다.
"""

from __future__ import annotations


class JsonFrameDecoder:
    """
    문자열 조각을 누적해 완성된 JSON 객체를 추출한다.

    JSON 문자열 내부의 중괄호는 구조의 끝으로
    잘못 인식하지 않도록 문자열 상태도 추적한다.
    """

    MAX_BUFFER_LENGTH = 16_384

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        """
        새 문자열 조각을 버퍼에 추가한다.

        완성된 JSON 객체가 있으면 문자열 목록으로 반환하고,
        아직 완성되지 않은 부분은 다음 입력을 위해 보관한다.
        """

        if not text:
            return []

        self._buffer += text

        # 비정상 데이터가 계속 누적되어 메모리를 차지하는 것을
        # 막기 위해 최대 버퍼 크기를 제한한다.
        self._trim_oversized_buffer()

        frames, remaining = self._extract_frames(
            self._buffer
        )

        self._buffer = remaining

        return frames

    def reset(self) -> None:
        """현재까지 누적한 불완전 데이터를 제거한다."""

        self._buffer = ""

    def _trim_oversized_buffer(self) -> None:
        """
        버퍼가 최대 크기를 초과하면
        가장 최근 JSON 시작 지점부터 남긴다.
        """

        if len(self._buffer) <= self.MAX_BUFFER_LENGTH:
            return

        last_start_index = self._buffer.rfind("{")

        if last_start_index == -1:
            self._buffer = ""
            return

        self._buffer = self._buffer[last_start_index:]

    @staticmethod
    def _extract_frames(
        source: str,
    ) -> tuple[list[str], str]:
        """
        source에서 완성된 JSON 객체들을 추출한다.

        반환값:
        - 완성된 JSON 문자열 목록
        - 아직 완성되지 않은 나머지 문자열
        """

        frames: list[str] = []

        object_start: int | None = None
        brace_depth = 0

        inside_string = False
        escape_next_character = False

        last_processed_index = -1

        for index, character in enumerate(source):
            last_processed_index = index

            # 아직 JSON 객체가 시작되지 않았다면
            # 첫 번째 여는 중괄호 전의 로그 문자열은 버린다.
            if object_start is None:
                if character != "{":
                    continue

                object_start = index
                brace_depth = 1
                inside_string = False
                escape_next_character = False
                continue

            # JSON 문자열 내부에서는 \" 같은 escape 문자를
            # 고려해야 문자열 종료를 정확히 판단할 수 있다.
            if inside_string:
                if escape_next_character:
                    escape_next_character = False
                    continue

                if character == "\\":
                    escape_next_character = True
                    continue

                if character == '"':
                    inside_string = False

                continue

            if character == '"':
                inside_string = True
                continue

            if character == "{":
                brace_depth += 1
                continue

            if character != "}":
                continue

            brace_depth -= 1

            if brace_depth != 0:
                continue

            frame = source[
                object_start:index + 1
            ]

            frames.append(frame)

            object_start = None
            inside_string = False
            escape_next_character = False

        # 아직 완성되지 않은 JSON이 있으면
        # 시작 중괄호부터 나머지를 보관한다.
        if object_start is not None:
            remaining = source[object_start:]
            return frames, remaining

        # 완성된 객체 뒤에 JSON이 아닌 로그만 남은 경우
        # 해당 로그는 보관하지 않는다.
        if last_processed_index >= 0:
            return frames, ""

        return frames, source
