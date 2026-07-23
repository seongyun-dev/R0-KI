package com.oneloop.patrol.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.service.PatrolService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/patrols")
public class PatrolController {

    private final PatrolService patrolService;

    @Operation(summary = "순찰 상세 조회", description = "순찰 경로, 배터리, 감지 이벤트 타임라인과 AI 요약을 조회합니다.")
    @GetMapping("/{patrolId}")
    public ApiResponse<PatrolDetailResponse> detail(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "순찰 ID", example = "1", required = true) @PathVariable
                    Long patrolId) {
        return ApiResponse.success(
                patrolService.findDetail(principal.getApartmentComplexId(), patrolId));
    }
}
