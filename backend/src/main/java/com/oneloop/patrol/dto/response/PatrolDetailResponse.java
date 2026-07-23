package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolAiSummary;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.domain.RoutePosition;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "순찰 상세 조회 응답")
public class PatrolDetailResponse {
    @Schema(description = "순찰 로봇 이름", example = "R-01")
    private String robotName;

    @Schema(description = "순찰 상태", example = "COMPLETED")
    private PatrolStatus patrolStatus;

    @Schema(description = "순찰 시작 시각", example = "2026-07-15T09:00:00")
    private LocalDateTime startedAt;

    @Schema(description = "순찰 종료 시각", example = "2026-07-15T09:42:00", nullable = true)
    private LocalDateTime endedAt;

    @Schema(description = "총 순찰 시간(분)", example = "42", nullable = true)
    private Integer totalDurationMinutes;

    @Schema(
            description = "순찰 지도 URL",
            example = "https://example.com/maps/patrol-map.png",
            nullable = true)
    private String mapUrl;

    @Schema(description = "순찰 중 방문한 체크포인트 목록")
    private List<PatrolRouteCheckpointResponse> route;

    @Schema(description = "순찰 시작·종료 배터리 잔량")
    private PatrolBatteryResponse battery;

    @Schema(description = "순찰 이동 좌표 목록")
    private List<PatrolRoutePointResponse> routePoints;

    @Schema(description = "순찰 중 감지 이벤트 타임라인")
    private List<PatrolTimelineResponse> timeline;

    @Schema(description = "AI 순찰 요약", nullable = true)
    private PatrolAiSummaryResponse aiSummary;

    public static PatrolDetailResponse of(
            Patrol patrol,
            String mapUrl,
            List<PatrolRouteCheckpointResponse> route,
            List<RoutePosition> routePositions,
            List<PatrolTimelineResponse> timeline,
            PatrolAiSummary aiSummary) {
        return PatrolDetailResponse.builder()
                .robotName(patrol.getRobot().getName())
                .patrolStatus(patrol.getStatus())
                .startedAt(patrol.getStartedAt())
                .endedAt(patrol.getEndedAt())
                .totalDurationMinutes(toMinutes(patrol.getTotalDuration()))
                .mapUrl(mapUrl)
                .route(route)
                .battery(PatrolBatteryResponse.from(patrol))
                .routePoints(routePositions.stream().map(PatrolRoutePointResponse::from).toList())
                .timeline(timeline)
                .aiSummary(aiSummary == null ? null : PatrolAiSummaryResponse.from(aiSummary))
                .build();
    }

    private static Integer toMinutes(Integer totalDurationSeconds) {
        return totalDurationSeconds == null ? null : totalDurationSeconds / 60;
    }
}
