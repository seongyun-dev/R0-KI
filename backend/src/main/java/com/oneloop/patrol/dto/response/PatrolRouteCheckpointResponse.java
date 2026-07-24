package com.oneloop.patrol.dto.response;

import com.oneloop.map.domain.CheckpointType;
import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "방문 체크포인트 응답")
public class PatrolRouteCheckpointResponse {
    @Schema(description = "체크포인트 ID", example = "1")
    private Long checkpointId;

    @Schema(description = "체크포인트 이름", example = "출발지")
    private String checkpointName;

    @Schema(description = "체크포인트 유형", example = "PARKING")
    private CheckpointType checkpointType;

    @Schema(description = "방문 순서", example = "1")
    private int sequence;

    public static PatrolRouteCheckpointResponse from(PatrolCheckpointVisit visit) {
        return PatrolRouteCheckpointResponse.builder()
                .checkpointId(visit.getCheckpoint().getId())
                .checkpointName(visit.getCheckpoint().getName())
                .checkpointType(visit.getCheckpoint().getType())
                .sequence(visit.getVisitSequence())
                .build();
    }
}
