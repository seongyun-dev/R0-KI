package com.oneloop.robot.dto.mqtt;

import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.domain.SensorStatus;
import java.math.BigDecimal;
import java.time.OffsetDateTime;

// hanbakwi/v1/robots/{robotKey}/status payload (5초 주기 + 변경 즉시)
public record RobotStatusMessage(
        int schemaVersion,
        String robotKey,
        BigDecimal battery,
        RobotStatus state,
        SensorStatus motor,
        SensorStatus camera,
        SensorStatus lidar,
        SensorStatus lineSensor,
        ObstacleInfo obstacle,
        OffsetDateTime timestamp) {}
