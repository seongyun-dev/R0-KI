package com.oneloop.robot.dto.response;

import com.oneloop.map.domain.CheckpointType;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 목록 조회 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RobotListResponse {

    @Schema(description = "로봇 ID", example = "1")
    private Long robotId;

    @Schema(description = "로봇 이름", example = "순찰로봇 1호")
    private String robotName;

    @Schema(description = "로봇 상태", example = "IDLE")
    private RobotStatus robotStatus;

    @Schema(description = "배터리 잔량(%) (로봇이 위치를 한 번도 보고하지 않은 경우 null)", example = "87.50", nullable = true)
    private BigDecimal batteryLevel;

    @Schema(description = "현재 위치가 속한 체크포인트 유형 (매칭되는 구역이 없으면 null)", example = "PARKING", nullable = true)
    private CheckpointType checkpointType;

    public static RobotListResponse of(PatrolRobot robot, CheckpointType checkpointType) {
        return RobotListResponse.builder()
                .robotId(robot.getId())
                .robotName(robot.getName())
                .robotStatus(robot.getStatus())
                .batteryLevel(robot.getBatteryLevel())
                .checkpointType(checkpointType)
                .build();
    }
}
