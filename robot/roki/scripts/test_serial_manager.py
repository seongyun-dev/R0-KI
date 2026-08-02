"""SerialManager가 연결 실패를 안전하게 처리하는지 확인하는 테스트."""

import logging
from typing import Any

from common.config_loader import load_serial_config
from serial_comm.serial_manager import (
    SerialConnectionSettings,
    SerialManager,
)


# 실제 장치를 실수로 열지 않도록 존재하지 않는 테스트 포트를 사용한다.
TEST_PORT = "/dev/roki_nonexistent_serial_port"


def create_test_serial_manager(
    config: dict[str, Any],
) -> SerialManager:
    """YAML 설정을 사용해 테스트용 SerialManager를 생성한다."""

    serial_config = config["serial"]

    settings = SerialConnectionSettings(
        port=TEST_PORT,
        baudrate=int(serial_config["baudrate"]),
        timeout_sec=float(serial_config["timeout_sec"]),
    )

    return SerialManager(settings=settings)


def main() -> None:
    """ESP32가 없어도 프로그램이 정상 종료되는지 확인한다."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
    )

    config = load_serial_config()
    manager = create_test_serial_manager(config)

    print("===== SerialManager 연결 실패 테스트 =====")
    print(f"테스트 포트: {manager.port}")

    connected = manager.connect()

    print(f"연결 결과: {connected}")
    print(f"연결 상태: {manager.is_connected()}")

    write_result = manager.write_line("PATROL_START")
    print(f"미연결 상태 전송 결과: {write_result}")

    read_result = manager.read_line()
    print(f"미연결 상태 수신 결과: {read_result}")

    manager.disconnect()

    print("SerialManager 테스트가 정상 종료되었습니다.")


if __name__ == "__main__":
    main()
