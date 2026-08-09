from pprint import pprint

from common.config_loader import (
    load_ai_config,
    load_lidar_config,
    load_mqtt_config,
    load_robot_config,
    load_serial_config,
)


def main() -> None:
    print("===== robot.yaml =====")
    pprint(load_robot_config())

    print("\n===== serial.yaml =====")
    pprint(load_serial_config())

    print("\n===== mqtt.yaml =====")
    pprint(load_mqtt_config())

    print("\n===== lidar.yaml =====")
    pprint(load_lidar_config())

    print("\n===== ai.yaml =====")
    pprint(load_ai_config())


if __name__ == "__main__":
    main()
