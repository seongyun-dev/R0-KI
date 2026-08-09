package com.oneloop.patrol.dto.request;

import com.oneloop.patrol.domain.PatrolStatus;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "순찰 상태 필터")
public enum PatrolStatusFilter {
    ALL(null),
    IN_PROGRESS(PatrolStatus.IN_PROGRESS),
    STOP_REQUESTED(PatrolStatus.STOP_REQUESTED),
    COMPLETED(PatrolStatus.COMPLETED),
    STOPPED(PatrolStatus.STOPPED),
    FAILED(PatrolStatus.FAILED);

    private final PatrolStatus patrolStatus;

    PatrolStatusFilter(PatrolStatus patrolStatus) {
        this.patrolStatus = patrolStatus;
    }

    public PatrolStatus toPatrolStatus() {
        return patrolStatus;
    }
}
