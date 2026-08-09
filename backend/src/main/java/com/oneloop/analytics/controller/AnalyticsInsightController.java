package com.oneloop.analytics.controller;

import com.oneloop.analytics.domain.AnalyticsInsightPeriodType;
import com.oneloop.analytics.dto.response.AnalyticsInsightResponse;
import com.oneloop.analytics.service.AnalyticsInsightService;
import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.security.CustomUserDetails;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * AI 인사이트 API.
 *
 * <p>통계 집계({@code /api/analytics/events/*})와 분리한다.
 * 이 API는 {@code analytics_ai_insights} 캐시 조회가 책임이다.
 *
 * <p>COMPLETED면 캐시만 반환. 없거나 PENDING/FAILED면 비동기로 GMS 생성을 트리거한다.
 */
@Tag(name = "Analytics Insight API", description = "통계 AI 인사이트 API")
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/analytics/insights")
public class AnalyticsInsightController {

    private final AnalyticsInsightService analyticsInsightService;

    @Operation(
            summary = "AI 인사이트 조회",
            description =
                    "주(WEEK) 또는 월(MONTH) AI 인사이트를 조회합니다. "
                            + "periodKey가 없으면 직전 완료 구간, 있으면 해당 키(예: 2026-W30, 2026-07) 구간입니다. "
                            + "진행 중·미래 구간 periodKey는 거절합니다. "
                            + "COMPLETED면 DB 캐시를 즉시 반환하고, "
                            + "없거나 PENDING/FAILED면 백그라운드에서 LLM 생성을 시작한 뒤 현재 상태를 반환합니다. "
                            + "생성 완료 여부는 동일 API를 다시 호출해 확인합니다.")
    @GetMapping
    public ApiResponse<AnalyticsInsightResponse> getInsight(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "기간 유형 (WEEK | MONTH)", required = true, example = "WEEK")
                    @RequestParam
                    AnalyticsInsightPeriodType periodType,
            @Parameter(
                            description =
                                    "기간 키 (선택). WEEK: 2026-W30, MONTH: 2026-07. "
                                            + "없으면 직전 완료 구간",
                            example = "2026-W30")
                    @RequestParam(required = false)
                    String periodKey) {
        return ApiResponse.success(
                "AI 인사이트를 조회했습니다.",
                analyticsInsightService.getInsight(
                        principal.getApartmentComplexId(), periodType, periodKey));
    }
}
