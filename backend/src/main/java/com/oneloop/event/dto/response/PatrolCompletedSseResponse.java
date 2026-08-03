package com.oneloop.event.dto.response;

import com.oneloop.patrol.domain.Patrol;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class PatrolCompletedSseResponse {

    private Long patrolId;
    private Long robotId;
    private String robotName;
    private LocalDateTime completedAt;

    public static PatrolCompletedSseResponse from(Patrol patrol) {
        return PatrolCompletedSseResponse.builder()
                .patrolId(patrol.getId())
                .robotId(patrol.getRobot().getId())
                .robotName(patrol.getRobot().getName())
                .completedAt(patrol.getEndedAt())
                .build();
    }
}
