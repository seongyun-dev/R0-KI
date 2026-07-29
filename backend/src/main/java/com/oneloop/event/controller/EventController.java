package com.oneloop.event.controller;

import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.event.dto.request.EventPeriodFilter;
import com.oneloop.event.dto.request.EventStatusChangeRequest;
import com.oneloop.event.dto.response.EventDetailResponse;
import com.oneloop.event.dto.response.EventListResponse;
import com.oneloop.event.dto.response.EventStatusChangeResponse;
import com.oneloop.event.service.EventService;
import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.response.PageResponse;
import com.oneloop.global.security.CustomUserDetails;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.data.domain.Sort.Direction.DESC;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/events")
public class EventController {

    private final EventService eventService;

    @Operation(summary = "이벤트 목록 조회", description = "소속 단지의 탐지 이벤트를 유형·상태·기간으로 필터링하여 최신순으로 조회합니다.")
    @GetMapping
    public ApiResponse<PageResponse<EventListResponse>> list(
            @AuthenticationPrincipal CustomUserDetails principal,
            // 미지정 시 전체 조회 (null로 바인딩)
            @Parameter(description = "이벤트 유형 (미지정 시 전체)") @RequestParam(required = false)
                    EventType type,
            // 미지정 시 전체 조회 (null로 바인딩)
            @Parameter(description = "처리 상태 (미지정 시 전체)") @RequestParam(required = false)
                    ProcessingStatus status,
            @Parameter(description = "기간 필터", example = "ALL")
                    @RequestParam(defaultValue = "ALL")
                    EventPeriodFilter period,
            @ParameterObject
                    @PageableDefault(size = 20, sort = "occurredAt", direction = DESC)
                    Pageable pageable) {
        return ApiResponse.success(
                eventService.findAll(
                        principal.getApartmentComplexId(), type, status, period, pageable));
    }

    @Operation(summary = "이벤트 상세 조회", description = "증거자료, 위치, 경과·처리 시간을 포함한 이벤트 상세 정보를 조회합니다.")
    @GetMapping("/{eventId}")
    public ApiResponse<EventDetailResponse> detail(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "이벤트 ID", example = "1", required = true) @PathVariable
                    Long eventId) {
        return ApiResponse.success(
                eventService.findDetail(principal.getApartmentComplexId(), eventId));
    }

    @Operation(summary = "이벤트 처리상태 변경", description = "이벤트의 처리 상태를 변경하고 처리이력을 자동으로 기록합니다.")
    @PatchMapping("/{eventId}/status")
    public ApiResponse<EventStatusChangeResponse> changeStatus(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "이벤트 ID", example = "1", required = true) @PathVariable
                    Long eventId,
            @Valid @RequestBody EventStatusChangeRequest request) {
        return ApiResponse.success(
                eventService.changeStatus(
                        principal.getApartmentComplexId(), principal.getMemberId(), eventId, request));
    }
}
