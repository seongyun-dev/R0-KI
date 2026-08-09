package com.oneloop.robot.dto.response;

import com.oneloop.robot.domain.ObstacleStatus;
import com.oneloop.robot.event.RobotObstacleEvent;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "로봇 장애물 감지/해제 SSE 이벤트")
@Getter
@Builder
public class RobotObstacleEventResponse {

    @Schema(description = "로봇 ID", example = "4")
    private Long robotId;

    @Schema(description = "장애물 상태", example = "STOP")
    private ObstacleStatus status;

    @Schema(description = "장애물 방향. CLEAR면 null", example = "FRONT")
    private String direction;

    @Schema(description = "장애물 안내 메시지. CLEAR면 null", example = "전방에 장애물이 있습니다.")
    private String message;

    public static RobotObstacleEventResponse from(RobotObstacleEvent event) {
        return RobotObstacleEventResponse.builder()
                .robotId(event.robotId())
                .status(event.status())
                .direction(event.direction())
                .message(event.message())
                .build();
    }
}
