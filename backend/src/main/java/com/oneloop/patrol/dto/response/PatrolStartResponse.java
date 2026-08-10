package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "순찰 시작 응답")
@Getter
@Builder
public class PatrolStartResponse {

    private Long patrolId;
    private Long robotId;
    private PatrolStatus patrolStatus;
    private LocalDateTime startedAt;

    public static PatrolStartResponse from(Patrol patrol) {
        return PatrolStartResponse.builder()
                .patrolId(patrol.getId())
                .robotId(patrol.getRobot().getId())
                .patrolStatus(patrol.getStatus())
                .startedAt(patrol.getStartedAt())
                .build();
    }
}
