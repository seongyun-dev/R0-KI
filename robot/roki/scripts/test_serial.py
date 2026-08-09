"""USB 시리얼 장치 탐색 기능을 확인하는 수동 테스트."""

from typing import Any

from common.config_loader import load_serial_config
from serial_comm.device_finder import SerialDeviceFinder


def read_device_finder_settings(
    config: dict[str, Any],
) -> tuple[str, int | None, int | None, list[str]]:
    """YAML 설정에서 장치 탐색에 필요한 값만 추출한다."""

    serial_config = config.get("serial", {})
    device_config = config.get("device", {})

    configured_port = str(
        serial_config.get("port", "auto")
    )

    preferred_vid = device_config.get("preferred_vid")
    preferred_pid = device_config.get("preferred_pid")

    allowed_port_prefixes = device_config.get(
        "allowed_port_prefixes",
        ["/dev/ttyUSB", "/dev/ttyACM"],
    )

    return (
        configured_port,
        preferred_vid,
        preferred_pid,
        allowed_port_prefixes,
    )


def print_connected_devices(
    finder: SerialDeviceFinder,
) -> None:
    """운영체제가 인식한 시리얼 장치 목록을 출력한다."""

    devices = finder.list_devices()

    print("===== 연결된 시리얼 장치 목록 =====")

    if not devices:
        print("연결된 USB 시리얼 장치가 없습니다.")
        return

    for index, device in enumerate(devices, start=1):
        print(f"{index}. {device.to_display_text()}")


def print_selected_device(
    finder: SerialDeviceFinder,
    configured_port: str,
    preferred_vid: int | None,
    preferred_pid: int | None,
) -> None:
    """자동 탐색으로 선택된 장치를 출력한다."""

    selected_device = finder.find_device(
        configured_port=configured_port,
        preferred_vid=preferred_vid,
        preferred_pid=preferred_pid,
    )

    print("\n===== 자동 선택 결과 =====")

    if selected_device is None:
        print("사용할 시리얼 장치를 찾지 못했습니다.")
        print("현재 ESP32가 없으므로 정상적인 결과입니다.")
        return

    print(
        f"선택된 장치: {selected_device.to_display_text()}"
    )


def main() -> None:
    """시리얼 장치 탐색 테스트를 실행한다."""

    config = load_serial_config()

    (
        configured_port,
        preferred_vid,
        preferred_pid,
        allowed_port_prefixes,
    ) = read_device_finder_settings(config)

    finder = SerialDeviceFinder(
        allowed_port_prefixes=allowed_port_prefixes,
    )

    print_connected_devices(finder)

    print_selected_device(
        finder=finder,
        configured_port=configured_port,
        preferred_vid=preferred_vid,
        preferred_pid=preferred_pid,
    )


if __name__ == "__main__":
    main()
