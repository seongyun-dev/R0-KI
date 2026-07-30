package com.oneloop.robot.event;

import com.oneloop.robot.domain.RobotStatus;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/** MQTT status로 보고된 로봇 상태와 배터리를 하단 목록에 전달하기 위한 내부 이벤트입니다. */
public record RobotStatusUpdatedEvent(
        Long apartmentComplexId,
        Long robotId,
        RobotStatus status,
        BigDecimal batteryLevel,
        LocalDateTime statusReportedAt) {}
