package com.oneloop.map.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.map.dto.request.WaypointBatchReplaceRequest;
import com.oneloop.map.dto.response.WaypointSetResponse;
import com.oneloop.map.service.NavigationWaypointService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/map/{mapId}/waypoints")
public class WaypointController {

    private final NavigationWaypointService navigationWaypointService;

    @GetMapping
    @Operation(summary = "순찰 경로 지점 조회", description = "현재 지도 버전의 순서 있는 순찰 경로를 조회합니다.")
    public ApiResponse<WaypointSetResponse> findAll(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable Long mapId) {
        return ApiResponse.success(
                navigationWaypointService.findAll(principal.getApartmentComplexId(), mapId));
    }

    @PutMapping
    @Operation(summary = "순찰 경로 지점 교체", description = "현재 지도 버전의 순찰 경로 전체를 원자적으로 교체합니다.")
    public ApiResponse<WaypointSetResponse> replaceAll(
            @AuthenticationPrincipal CustomUserDetails principal,
            @PathVariable Long mapId,
            @Valid @RequestBody WaypointBatchReplaceRequest request) {
        return ApiResponse.success(
                "순찰 경로가 저장되었습니다.",
                navigationWaypointService.replaceAll(
                        principal.getApartmentComplexId(), mapId, request));
    }
}
