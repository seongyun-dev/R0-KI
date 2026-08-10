package com.oneloop.robot.event;

import com.oneloop.robot.domain.PatrolRobot;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/** MQTT pose로 보고된 로봇의 최신 위치를 지도에 전달하기 위한 내부 이벤트입니다. */
public record RobotLocationUpdatedEvent(
        Long apartmentComplexId,
        Long robotId,
        BigDecimal x,
        BigDecimal y,
        BigDecimal heading,
        LocalDateTime locationUpdatedAt) {

    public static RobotLocationUpdatedEvent from(PatrolRobot robot) {
        return new RobotLocationUpdatedEvent(
                robot.getApartmentComplex().getId(),
                robot.getId(),
                robot.getXCoordinate(),
                robot.getYCoordinate(),
                robot.getHeading(),
                robot.getLocationUpdatedAt());
    }
}
