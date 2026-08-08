"""Fail-closed LaserScan relay used only at the slam_toolbox boundary."""

from __future__ import annotations

import threading
from typing import Any, Callable


class LaserScanGate:
    """Relay messages unchanged while open; default and failures are closed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open = False

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._open

    def open(self) -> bool:
        with self._lock:
            self._open = True
            return self._open

    def close(self) -> bool:
        with self._lock:
            self._open = False
            return self._open

    def relay(self, message: Any, publish: Callable[[Any], None]) -> bool:
        """Publish the same object while open and close on relay failure."""

        with self._lock:
            if not self._open:
                return False
            try:
                publish(message)
            except Exception:
                self._open = False
                raise
            return True


def main() -> None:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    from std_srvs.srv import SetBool

    class ScanGateNode(Node):
        def __init__(self) -> None:
            super().__init__("roki_scan_gate")
            input_topic = str(self.declare_parameter("input_topic", "/scan").value)
            output_topic = str(
                self.declare_parameter("output_topic", "/slam_scan").value
            )
            service_name = str(
                self.declare_parameter(
                    "control_service", "/roki/scan_gate/set_enabled"
                ).value
            )
            self._gate = LaserScanGate()
            self._publisher = self.create_publisher(
                LaserScan, output_topic, qos_profile_sensor_data
            )
            self._subscription = self.create_subscription(
                LaserScan,
                input_topic,
                self._on_scan,
                qos_profile_sensor_data,
            )
            self._service = self.create_service(
                SetBool, service_name, self._set_enabled
            )
            self.get_logger().info(
                f"scan gate CLOSED input={input_topic} output={output_topic}"
            )

        def _on_scan(self, message: Any) -> None:
            try:
                self._gate.relay(message, self._publisher.publish)
            except Exception as exc:
                self.get_logger().error(
                    "scan relay failed closed: " + type(exc).__name__
                )

        def _set_enabled(self, request: Any, response: Any) -> Any:
            if bool(request.data):
                self._gate.open()
                state = "OPEN"
            else:
                self._gate.close()
                state = "CLOSED"
            response.success = True
            response.message = state
            self.get_logger().info(f"scan gate {state}")
            return response

    rclpy.init(args=None)
    node = ScanGateNode()
    try:
        rclpy.spin(node)
    finally:
        node._gate.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
