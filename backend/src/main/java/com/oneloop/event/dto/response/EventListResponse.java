package com.oneloop.event.dto.response;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.event.domain.RiskLevel;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "이벤트 목록 조회 응답")
public class EventListResponse {
    @Schema(description = "이벤트 ID", example = "501")
    private Long eventId;

    @Schema(description = "탐지 시각", example = "2026-07-15T09:12:00")
    private LocalDateTime occurredAt;

    @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
    private EventType type;

    @Schema(description = "발생 위치가 속한 체크포인트 이름 (매칭되는 구역이 없으면 null)", example = "주차장", nullable = true)
    private String location;

    @Schema(description = "탐지 로봇 이름", example = "순찰로봇 1호")
    private String robotName;

    @Schema(description = "위험도", example = "NORMAL")
    private RiskLevel riskLevel;

    @Schema(description = "처리 상태", example = "DETECTED")
    private ProcessingStatus status;

    @Schema(description = "담당자 이름 (처리이력이 없으면 null)", example = "김관리", nullable = true)
    private String assignee;

    public static EventListResponse of(DetectedEvent event, String location, String assignee) {
        return EventListResponse.builder()
                .eventId(event.getId())
                .occurredAt(event.getOccurredAt())
                .type(event.getType())
                .location(location)
                .robotName(event.getRobot().getName())
                .riskLevel(event.getRiskLevel())
                .status(event.getProcessingStatus())
                .assignee(assignee)
                .build();
    }
}
