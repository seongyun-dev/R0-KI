package com.oneloop.patrol.dto.response;

import com.oneloop.map.domain.Checkpoint;
import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "방문 체크포인트 응답")
public class PatrolRouteCheckpointResponse {
    @Schema(description = "체크포인트 이름", example = "출발지")
    private String checkpointName;

    @Schema(description = "방문 순서", example = "1")
    private int sequence;

    /* 아래 좌표·유형은 "이 순찰 당시의 구역" 그대로다.
       방문 기록이 참조하는 체크포인트 행에서 읽으므로, 이후 구역을 다시 등록해
       그 행이 비활성(active=0)이 되어도 값이 변하지 않는다.
       순찰 상세 지도는 현재 활성 구역이 아니라 이 좌표로 구역을 그려야
       과거 순찰이 그때 구역과 함께 표시된다. */

    @Schema(description = "체크포인트 유형", example = "PARKING")
    private String checkpointType;

    @Schema(description = "구역 최소 X (지도 월드 좌표, m)", example = "-1.421")
    private BigDecimal minX;

    @Schema(description = "구역 최소 Y", example = "-3.589")
    private BigDecimal minY;

    @Schema(description = "구역 최대 X", example = "-0.425")
    private BigDecimal maxX;

    @Schema(description = "구역 최대 Y", example = "-1.446")
    private BigDecimal maxY;

    public static PatrolRouteCheckpointResponse from(PatrolCheckpointVisit visit) {
        Checkpoint checkpoint = visit.getCheckpoint();
        return PatrolRouteCheckpointResponse.builder()
                .checkpointName(checkpoint.getName())
                .sequence(visit.getVisitSequence())
                .checkpointType(checkpoint.getType().name())
                .minX(checkpoint.getMinX())
                .minY(checkpoint.getMinY())
                .maxX(checkpoint.getMaxX())
                .maxY(checkpoint.getMaxY())
                .build();
    }
}
