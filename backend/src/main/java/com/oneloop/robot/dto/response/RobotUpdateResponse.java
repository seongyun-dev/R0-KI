package com.oneloop.robot.dto.response;

import com.oneloop.robot.domain.PatrolRobot;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 수정 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RobotUpdateResponse {

    @Schema(description = "로봇 ID", example = "1")
    private Long robotId;

    @Schema(description = "로봇 이름", example = "순찰로봇 1호")
    private String robotName;

    @Schema(description = "수정일시")
    private LocalDateTime updatedAt;

    public static RobotUpdateResponse from(PatrolRobot robot) {
        return RobotUpdateResponse.builder()
                .robotId(robot.getId())
                .robotName(robot.getName())
                .updatedAt(robot.getUpdatedAt())
                .build();
    }
}
