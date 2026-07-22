package com.oneloop.robot.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 현황 통계 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class RobotStatsResponse {

    @Schema(description = "전체 로봇 수", example = "10")
    private long totalCount;

    @Schema(description = "순찰중인 로봇 수", example = "4")
    private long patrollingCount;

    @Schema(description = "대기/충전중인 로봇 수", example = "5")
    private long idleOrChargingCount;
}
