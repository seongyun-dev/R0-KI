package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import com.oneloop.patrol.domain.PatrolStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰 목록 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PatrolListResponse {

    @Schema(description = "순찰 ID", example = "1")
    private Long patrolId;

    @Schema(description = "순찰 로봇 이름", example = "R-01")
    private String robotName;

    @Schema(description = "순찰 시작 시각", example = "2026-07-24T09:00:00")
    private LocalDateTime startedAt;

    @Schema(description = "순찰 종료 시각", example = "2026-07-24T09:35:00", nullable = true)
    private LocalDateTime endedAt;

    @Schema(description = "순찰 상태", example = "COMPLETED")
    private PatrolStatus patrolStatus;

    @Schema(description = "감지된 이벤트 건수", example = "2")
    private int detectedEventCount;

    @Schema(description = "방문한 체크포인트 경로")
    private List<PatrolRouteCheckpointResponse> route;

    public static PatrolListResponse of(
            Patrol patrol, List<PatrolCheckpointVisit> checkpointVisits) {
        return PatrolListResponse.builder()
                .patrolId(patrol.getId())
                .robotName(patrol.getRobot().getName())
                .startedAt(patrol.getStartedAt())
                .endedAt(patrol.getEndedAt())
                .patrolStatus(patrol.getStatus())
                .detectedEventCount(patrol.getDetectedEventCount())
                .route(
                        checkpointVisits.stream()
                                .map(PatrolRouteCheckpointResponse::from)
                                .toList())
                .build();
    }
}
