package com.oneloop.analytics.controller;

import com.oneloop.analytics.dto.request.AnalyticsBucket;
import com.oneloop.analytics.dto.request.ZoneSort;
import com.oneloop.analytics.dto.response.ByTypeResponse;
import com.oneloop.analytics.dto.response.ByZoneResponse;
import com.oneloop.analytics.dto.response.OverviewResponse;
import com.oneloop.analytics.dto.response.TrendResponse;
import com.oneloop.analytics.service.AnalyticsQueryService;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.security.CustomUserDetails;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.OffsetDateTime;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 이벤트 분석 API 진입점.
 *
 * <p>프론트(관리자 웹)가 대시보드 그래프/카드를 그릴 때 호출한다.
 * 인증된 관리자의 apartmentComplexId로 단지 범위를 강제하므로,
 * URL만 알아도 다른 단지 통계를 볼 수 없다.
 *
 * <p>현재 제공 API:
 * - GET /overview : 상단 요약 카드용
 * - GET /trend : 일/주/월 추이 차트용
 * - GET /by-type : 유형별 건수/비율/증감
 * - GET /by-zone : 구역별 건수/순찰 대비/최다 구역
 */
@Tag(name = "Analytics API", description = "이벤트 분석/통계 API")
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/analytics/events")
public class AnalyticsController {

    private final AnalyticsQueryService analyticsQueryService;

    @Operation(
            summary = "전체 현황 요약",
            description =
                    "대시보드 상단 카드용 핵심 이벤트 요약 통계를 조회합니다. "
                            + "전체/오늘 건수, 최다 유형·구역, 이전 동기간 대비 증감을 반환합니다.")
    @GetMapping("/overview")
    public ApiResponse<OverviewResponse> overview(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "조회 시작 시각 (ISO-8601, 예: 2026-07-01T00:00:00+09:00)", required = true)
                    @RequestParam
                    OffsetDateTime from,
            @Parameter(description = "조회 종료 시각 (ISO-8601, 예: 2026-07-31T23:59:59+09:00)", required = true)
                    @RequestParam
                    OffsetDateTime to,
            @Parameter(description = "이전 동기간 대비 증감 포함 여부 (기본 true)")
                    @RequestParam(defaultValue = "true")
                    boolean compare,
            @Parameter(description = "구역 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> zoneIds,
            @Parameter(description = "이벤트 유형 목록 (미지정 시 전체)")
                    @RequestParam(required = false)
                    List<EventType> eventTypes,
            @Parameter(description = "로봇 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> robotIds) {
        return ApiResponse.success(
                "요약 통계를 조회했습니다.",
                analyticsQueryService.getOverview(
                        principal.getApartmentComplexId(),
                        from.toLocalDateTime(),
                        to.toLocalDateTime(),
                        compare,
                        zoneIds,
                        eventTypes,
                        robotIds));
    }

    @Operation(
            summary = "기간별 발생 추이",
            description =
                    "일/주/월 단위로 이벤트 발생 추이를 조회합니다. "
                            + "차트 X축(시간)과 Y축(건수), 유형·상태별 상세 건수를 반환합니다.")
    @GetMapping("/trend")
    public ApiResponse<TrendResponse> trend(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "조회 시작 시각 (ISO-8601)", required = true) @RequestParam
                    OffsetDateTime from,
            @Parameter(description = "조회 종료 시각 (ISO-8601)", required = true) @RequestParam
                    OffsetDateTime to,
            @Parameter(description = "집계 단위 (day/week/month)", required = true, example = "day")
                    @RequestParam
                    AnalyticsBucket bucket,
            @Parameter(description = "구역 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> zoneIds,
            @Parameter(description = "이벤트 유형 목록 (미지정 시 전체)")
                    @RequestParam(required = false)
                    List<EventType> eventTypes,
            @Parameter(description = "로봇 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> robotIds,
            @Parameter(description = "처리 상태 목록 (미지정 시 전체)")
                    @RequestParam(required = false)
                    List<ProcessingStatus> statuses) {
        return ApiResponse.success(
                "기간별 추이를 조회했습니다.",
                analyticsQueryService.getTrend(
                        principal.getApartmentComplexId(),
                        from.toLocalDateTime(),
                        to.toLocalDateTime(),
                        bucket,
                        zoneIds,
                        eventTypes,
                        robotIds,
                        statuses));
    }

    @Operation(
            summary = "이벤트 유형별 통계",
            description =
                    "이벤트 유형별 발생 건수, 전체 대비 비율, 이전 동기간 대비 증감을 조회합니다. "
                            + "막대/파이 차트용 데이터입니다.")
    @GetMapping("/by-type")
    public ApiResponse<ByTypeResponse> byType(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "조회 시작 시각 (ISO-8601)", required = true) @RequestParam
                    OffsetDateTime from,
            @Parameter(description = "조회 종료 시각 (ISO-8601)", required = true) @RequestParam
                    OffsetDateTime to,
            @Parameter(description = "이전 동기간 대비 증감 포함 여부 (기본 true)")
                    @RequestParam(defaultValue = "true")
                    boolean compare,
            @Parameter(description = "구역 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> zoneIds,
            @Parameter(description = "로봇 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> robotIds,
            @Parameter(description = "처리 상태 목록 (미지정 시 전체)")
                    @RequestParam(required = false)
                    List<ProcessingStatus> statuses) {
        return ApiResponse.success(
                "유형별 통계를 조회했습니다.",
                analyticsQueryService.getByType(
                        principal.getApartmentComplexId(),
                        from.toLocalDateTime(),
                        to.toLocalDateTime(),
                        compare,
                        zoneIds,
                        robotIds,
                        statuses));
    }

    @Operation(
            summary = "구역별 이벤트 통계",
            description =
                    "구역별 이벤트 건수, 순찰 방문 대비 비율, 최다 발생 구역을 조회합니다. "
                            + "구역 막대 차트 및 위험 구역 하이라이트용 데이터입니다.")
    @GetMapping("/by-zone")
    public ApiResponse<ByZoneResponse> byZone(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "조회 시작 시각 (ISO-8601)", required = true) @RequestParam
                    OffsetDateTime from,
            @Parameter(description = "조회 종료 시각 (ISO-8601)", required = true) @RequestParam
                    OffsetDateTime to,
            @Parameter(description = "이벤트 유형 목록 (미지정 시 전체)")
                    @RequestParam(required = false)
                    List<EventType> eventTypes,
            @Parameter(description = "로봇 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> robotIds,
            @Parameter(description = "처리 상태 목록 (미지정 시 전체)")
                    @RequestParam(required = false)
                    List<ProcessingStatus> statuses,
            // count_desc(기본) | rate_desc
            @Parameter(description = "정렬 (count_desc | rate_desc)", example = "count_desc")
                    @RequestParam(defaultValue = "count_desc")
                    ZoneSort sort) {
        return ApiResponse.success(
                "구역별 통계를 조회했습니다.",
                analyticsQueryService.getByZone(
                        principal.getApartmentComplexId(),
                        from.toLocalDateTime(),
                        to.toLocalDateTime(),
                        eventTypes,
                        robotIds,
                        statuses,
                        sort));
    }
}
