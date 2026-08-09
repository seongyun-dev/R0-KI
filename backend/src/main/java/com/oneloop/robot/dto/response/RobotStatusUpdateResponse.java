package com.oneloop.robot.dto.response;

import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.event.RobotStatusUpdatedEvent;
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
public class RobotStatusUpdateResponse {

    private Long robotId;
    private RobotStatus status;
    private BigDecimal batteryLevel;
    private LocalDateTime statusReportedAt;

    public static RobotStatusUpdateResponse from(RobotStatusUpdatedEvent event) {
        return RobotStatusUpdateResponse.builder()
                .robotId(event.robotId())
                .status(event.status())
                .batteryLevel(event.batteryLevel())
                .statusReportedAt(event.statusReportedAt())
                .build();
    }
}
