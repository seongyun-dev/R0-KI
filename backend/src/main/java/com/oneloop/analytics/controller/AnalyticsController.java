package com.oneloop.analytics.controller;

import com.oneloop.analytics.dto.response.OverviewResponse;
import com.oneloop.analytics.service.AnalyticsQueryService;
import com.oneloop.event.domain.EventType;
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
 * <p>Step 1에서 제공하는 API:
 * - GET /overview : 상단 요약 카드용
 * (이후 trend / by-type / by-zone 등이 같은 컨트롤러에 추가될 예정)
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
            // JWT에서 꺼낸 로그인 사용자. 단지 ID는 여기서만 신뢰한다.
            @AuthenticationPrincipal CustomUserDetails principal,
            // OffsetDateTime: Postman에서 +09:00(%2B09:00)까지 받을 수 있게 함.
            // 서비스 내부 집계는 LocalDateTime으로 변환해 사용한다.
            @Parameter(description = "조회 시작 시각 (ISO-8601, 예: 2026-07-01T00:00:00+09:00)", required = true)
                    @RequestParam
                    OffsetDateTime from,
            @Parameter(description = "조회 종료 시각 (ISO-8601, 예: 2026-07-31T23:59:59+09:00)", required = true)
                    @RequestParam
                    OffsetDateTime to,
            // true면 이전 동기간 대비 증감(delta) 계산. 기본 true.
            @Parameter(description = "이전 동기간 대비 증감 포함 여부 (기본 true)")
                    @RequestParam(defaultValue = "true")
                    boolean compare,
            // 미지정 시 전체 구역. 복수면 zoneIds=1&zoneIds=2 형태.
            @Parameter(description = "구역 ID 목록 (미지정 시 전체)") @RequestParam(required = false)
                    List<Long> zoneIds,
            // 미지정 시 전체 유형. 예: eventTypes=ILLEGAL_PARKING
            @Parameter(description = "이벤트 유형 목록 (미지정 시 전체)")
                    @RequestParam(required = false)
                    List<EventType> eventTypes,
            // 미지정 시 전체 로봇
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
}
