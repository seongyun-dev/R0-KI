package com.oneloop.notification.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.response.PageResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.notification.dto.response.NotificationDetailResponse;
import com.oneloop.notification.dto.response.NotificationListResponse;
import com.oneloop.notification.service.NotificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import lombok.RequiredArgsConstructor;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.data.domain.Sort.Direction.DESC;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationService notificationService;

    @Operation(summary = "알림 목록 조회", description = "소속 단지의 알림 발송 이력을 최신순으로 조회합니다.")
    @GetMapping
    public ApiResponse<PageResponse<NotificationListResponse>> list(
            @AuthenticationPrincipal CustomUserDetails principal,
            @ParameterObject @PageableDefault(size = 20, sort = "id", direction = DESC) Pageable pageable) {
        return ApiResponse.success(
                notificationService.findAll(principal.getApartmentComplexId(), pageable));
    }

    @Operation(summary = "알림 상세 조회", description = "알림 발송 이력 하나를 상세 조회합니다.")
    @GetMapping("/{notificationId}")
    public ApiResponse<NotificationDetailResponse> detail(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "알림 ID", example = "1", required = true) @PathVariable
                    Long notificationId) {
        return ApiResponse.success(
                notificationService.findDetail(principal.getApartmentComplexId(), notificationId));
    }
}
