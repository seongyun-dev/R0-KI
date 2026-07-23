package com.oneloop.robot.dto.response;

import com.oneloop.robot.domain.PatrolRobot;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 삭제 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RobotDeleteResponse {

    @Schema(description = "로봇 ID", example = "1")
    private Long robotId;

    @Schema(description = "삭제일시")
    private LocalDateTime deletedAt;

    public static RobotDeleteResponse from(PatrolRobot robot) {
        return RobotDeleteResponse.builder()
                .robotId(robot.getId())
                .deletedAt(robot.getUpdatedAt())
                .build();
    }
}
