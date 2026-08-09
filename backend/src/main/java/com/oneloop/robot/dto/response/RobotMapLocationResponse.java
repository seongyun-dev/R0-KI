package com.oneloop.robot.dto.response;

import com.oneloop.patrol.domain.RoutePosition;
import com.oneloop.patrol.dto.response.PatrolRoutePointResponse;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "지도에 표시할 로봇 최신 위치와 현재 순찰 이동 경로")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RobotMapLocationResponse {

    private Long robotId;
    private String robotName;
    private RobotStatus status;
    private BigDecimal x;
    private BigDecimal y;
    private BigDecimal heading;
    private LocalDateTime locationUpdatedAt;
    private List<PatrolRoutePointResponse> routePoints;

    public static RobotMapLocationResponse of(
            PatrolRobot robot, List<RoutePosition> routePositions) {
        return RobotMapLocationResponse.builder()
                .robotId(robot.getId())
                .robotName(robot.getName())
                .status(robot.getStatus())
                .x(robot.getXCoordinate())
                .y(robot.getYCoordinate())
                .heading(robot.getHeading())
                .locationUpdatedAt(robot.getLocationUpdatedAt())
                .routePoints(routePositions.stream().map(PatrolRoutePointResponse::from).toList())
                .build();
    }
}
