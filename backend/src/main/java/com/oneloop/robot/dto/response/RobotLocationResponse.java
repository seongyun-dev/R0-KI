package com.oneloop.robot.dto.response;

import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.event.RobotLocationUpdatedEvent;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RobotLocationResponse {

    private Long robotId;
    private BigDecimal x;
    private BigDecimal y;
    private BigDecimal heading;
    private LocalDateTime locationUpdatedAt;

    public static RobotLocationResponse from(PatrolRobot robot) {
        return RobotLocationResponse.builder()
                .robotId(robot.getId())
                .x(robot.getXCoordinate())
                .y(robot.getYCoordinate())
                .heading(robot.getHeading())
                .locationUpdatedAt(robot.getLocationUpdatedAt())
                .build();
    }

    public static RobotLocationResponse from(RobotLocationUpdatedEvent event) {
        return RobotLocationResponse.builder()
                .robotId(event.robotId())
                .x(event.x())
                .y(event.y())
                .heading(event.heading())
                .locationUpdatedAt(event.locationUpdatedAt())
                .build();
    }
}
