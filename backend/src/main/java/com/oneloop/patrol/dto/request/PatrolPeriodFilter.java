package com.oneloop.patrol.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "순찰 기간 필터")
public enum PatrolPeriodFilter {
    ALL,
    TODAY,
    LAST_7_DAYS,
    PREVIOUS_WEEK
}
