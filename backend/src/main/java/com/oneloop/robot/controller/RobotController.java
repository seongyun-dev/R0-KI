package com.oneloop.robot.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.response.PageResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.robot.dto.request.RobotRegisterRequest;
import com.oneloop.robot.dto.response.RobotDetailResponse;
import com.oneloop.robot.dto.response.RobotListResponse;
import com.oneloop.robot.dto.response.RobotRegisterResponse;
import com.oneloop.robot.dto.response.RobotStatsResponse;
import com.oneloop.robot.service.RobotService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/robots")
public class RobotController {

    private final RobotService robotService;

    @Operation(summary = "로봇 등록", description = "새로운 순찰로봇을 등록합니다.")
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<RobotRegisterResponse> register(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Valid @RequestBody RobotRegisterRequest request) {
        return ApiResponse.success(
                "로봇이 등록되었습니다.",
                robotService.register(principal.getApartmentComplexId(), request));
    }

    @Operation(summary = "로봇 목록 조회", description = "등록된 순찰로봇 목록을 조회합니다.")
    @GetMapping
    public ApiResponse<PageResponse<RobotListResponse>> list(
            @AuthenticationPrincipal CustomUserDetails principal, @ParameterObject Pageable pageable) {
        return ApiResponse.success(
                robotService.findAll(principal.getApartmentComplexId(), pageable));
    }

    @Operation(summary = "로봇 현황 통계 조회", description = "순찰로봇 현황(전체/순찰중/대기·충전중 수)을 조회합니다.")
    @GetMapping("/stats")
    public ApiResponse<RobotStatsResponse> stats(@AuthenticationPrincipal CustomUserDetails principal) {
        return ApiResponse.success(robotService.getStats(principal.getApartmentComplexId()));
    }

    @Operation(summary = "로봇 상세 조회", description = "순찰로봇 하나를 상세 조회합니다.")
    @GetMapping("/{robotId}")
    public ApiResponse<RobotDetailResponse> detail(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable Long robotId) {
        return ApiResponse.success(robotService.findById(principal.getApartmentComplexId(), robotId));
    }
}
