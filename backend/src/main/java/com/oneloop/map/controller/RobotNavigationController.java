package com.oneloop.map.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.map.dto.response.NavigationConfigResponse;
import com.oneloop.map.service.RobotNavigationConfigService;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/robot/navigation-config")
public class RobotNavigationController {

    private final RobotNavigationConfigService robotNavigationConfigService;

    @GetMapping
    @Operation(summary = "로봇 주행 설정 조회", description = "인증된 로봇 소속 단지의 최신 지도·구역·순찰 경로를 조회합니다.")
    public ApiResponse<NavigationConfigResponse> get(@AuthenticationPrincipal Long robotId) {
        return ApiResponse.success(robotNavigationConfigService.get(robotId));
    }
}
