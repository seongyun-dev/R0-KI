package com.oneloop.robot.dto.response;

import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class RobotResponse {

    @Schema(description = "로봇 ID", example = "1")
    private Long robotId;

    @Schema(description = "로봇 이름", example = "순찰로봇 1호")
    private String robotName;

    @Schema(description = "로봇 시리얼 번호", example = "ROBOT-0001")
    private String robotSerialNumber;

    @Schema(description = "로봇 상태", example = "IDLE")
    private RobotStatus robotStatus;

    @Schema(description = "등록일시")
    private LocalDateTime registeredAt;

    public static RobotResponse from(PatrolRobot robot) {
        return new RobotResponse(
                robot.getId(),
                robot.getName(),
                robot.getSerialNumber(),
                robot.getStatus(),
                robot.getCreatedAt());
    }
}
