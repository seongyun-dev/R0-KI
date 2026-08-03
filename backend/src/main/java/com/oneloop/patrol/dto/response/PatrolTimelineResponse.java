package com.oneloop.patrol.dto.response;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "순찰 타임라인 기록 응답")
public class PatrolTimelineResponse {
    @Schema(description = "기록 시각", example = "2026-07-15T09:12:00")
    private LocalDateTime recordedAt;

    @Schema(description = "이벤트 발생 체크포인트", example = "주차장", nullable = true)
    private String checkpointName;

    @Schema(description = "이벤트 ID", example = "501")
    private Long eventId;

    @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
    private EventType eventType;

    @Schema(description = "처리 상태", example = "DETECTED")
    private ProcessingStatus processingStatus;

    @Schema(description = "이벤트 발생 X 좌표", example = "13.000", nullable = true)
    private BigDecimal xCoordinate;

    @Schema(description = "이벤트 발생 Y 좌표", example = "8.000", nullable = true)
    private BigDecimal yCoordinate;

    public static PatrolTimelineResponse of(DetectedEvent event, String checkpointName) {
        return PatrolTimelineResponse.builder()
                .recordedAt(event.getOccurredAt())
                .checkpointName(checkpointName)
                .eventId(event.getId())
                .eventType(event.getType())
                .processingStatus(event.getProcessingStatus())
                .xCoordinate(event.getX())
                .yCoordinate(event.getY())
                .build();
    }
}
