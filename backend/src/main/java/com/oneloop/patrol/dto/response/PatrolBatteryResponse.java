package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.Patrol;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "순찰 배터리 정보 응답")
public class PatrolBatteryResponse {
    @Schema(description = "순찰 시작 시 배터리 잔량(%)", example = "100", nullable = true)
    private BigDecimal startLevel;

    @Schema(description = "순찰 종료 시 배터리 잔량(%)", example = "82", nullable = true)
    private BigDecimal endLevel;

    public static PatrolBatteryResponse from(Patrol patrol) {
        return PatrolBatteryResponse.builder()
                .startLevel(patrol.getStartBatteryLevel())
                .endLevel(patrol.getEndBatteryLevel())
                .build();
    }
}
