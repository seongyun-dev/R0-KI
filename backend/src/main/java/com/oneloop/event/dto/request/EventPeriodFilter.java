package com.oneloop.event.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "이벤트 기간 필터")
public enum EventPeriodFilter {
    ALL,
    TODAY,
    LAST_7_DAYS
}
