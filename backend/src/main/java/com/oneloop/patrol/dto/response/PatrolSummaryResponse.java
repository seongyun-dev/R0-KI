package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰 기록 요약 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class PatrolSummaryResponse {

    @Schema(description = "순찰 ID", example = "1")
    private Long patrolId;

    @Schema(description = "순찰 상태", example = "COMPLETED")
    private PatrolStatus patrolStatus;

    @Schema(description = "순찰 시작 시각")
    private LocalDateTime startedAt;

    @Schema(description = "순찰 종료 시각 (진행중이면 null)", nullable = true)
    private LocalDateTime endedAt;

    @Schema(description = "감지된 이벤트 건수", example = "2")
    private int detectedEventCount;

    public static PatrolSummaryResponse from(Patrol patrol) {
        return new PatrolSummaryResponse(
                patrol.getId(),
                patrol.getStatus(),
                patrol.getStartedAt(),
                patrol.getEndedAt(),
                patrol.getDetectedEventCount());
    }
}
