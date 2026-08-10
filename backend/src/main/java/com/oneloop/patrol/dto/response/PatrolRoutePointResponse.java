package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.RoutePosition;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "순찰 이동 좌표 응답")
public class PatrolRoutePointResponse {
    @Schema(description = "X 좌표", example = "10.125")
    private BigDecimal xCoordinate;

    @Schema(description = "Y 좌표", example = "20.350")
    private BigDecimal yCoordinate;

    @Schema(description = "좌표 기록 시각", example = "2026-07-15T09:00:00")
    private LocalDateTime recordedAt;

    public static PatrolRoutePointResponse from(RoutePosition position) {
        return PatrolRoutePointResponse.builder()
                .xCoordinate(position.getX())
                .yCoordinate(position.getY())
                .recordedAt(position.getRecordedAt())
                .build();
    }
}
