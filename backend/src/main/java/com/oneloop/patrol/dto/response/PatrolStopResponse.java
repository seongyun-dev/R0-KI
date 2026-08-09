package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class PatrolStopResponse {

    private Long patrolId;
    private Long robotId;
    private PatrolStatus patrolStatus;

    public static PatrolStopResponse from(Patrol patrol) {
        return PatrolStopResponse.builder()
                .patrolId(patrol.getId())
                .robotId(patrol.getRobot().getId())
                .patrolStatus(patrol.getStatus())
                .build();
    }
}
