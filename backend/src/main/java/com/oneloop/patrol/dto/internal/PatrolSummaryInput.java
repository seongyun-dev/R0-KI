package com.oneloop.patrol.dto.internal;

import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.event.domain.RiskLevel;
import com.oneloop.map.domain.CheckpointType;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PatrolSummaryInput {

    private Long patrolId;
    private String robotName;
    private LocalDateTime startedAt;
    private LocalDateTime endedAt;
    private Integer durationMinutes;
    private BigDecimal startBatteryLevel;
    private BigDecimal endBatteryLevel;
    private List<VisitedCheckpoint> visitedCheckpoints;
    private List<DetectedEventInput> events;

    @Getter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class VisitedCheckpoint {
        private int sequence;
        private CheckpointType checkpointType;
        private String checkpointName;
        private LocalDateTime visitedAt;
    }

    @Getter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class DetectedEventInput {
        private Long eventId;
        private EventType eventType;
        private String title;
        private String details;
        private RiskLevel riskLevel;
        private LocalDateTime occurredAt;
        private String checkpointName;
        private ProcessingStatus processingStatus;
    }
}
