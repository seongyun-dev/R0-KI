package com.oneloop.map.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.map.dto.request.ZoneBatchCreateRequest;
import com.oneloop.map.dto.response.ZoneResponse;
import com.oneloop.map.service.ZoneService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/map/{mapId}/zones")
public class ZoneController {

    private final ZoneService zoneService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
            summary = "지도 구역 일괄 생성",
            description = "지도에서 드래그한 사각형 구역 여러 개를 한 요청으로 생성합니다.")
    public ApiResponse<List<ZoneResponse>> create(
            @AuthenticationPrincipal CustomUserDetails principal,
            @PathVariable Long mapId,
            @Valid @RequestBody ZoneBatchCreateRequest request) {
        return ApiResponse.success(
                "지도 구역이 생성되었습니다.",
                zoneService.createAll(principal.getApartmentComplexId(), mapId, request));
    }

    @PutMapping
    @Operation(
            summary = "지도 구역 전체 교체",
            description = "기존 체크포인트를 모두 제거하고 요청한 구역 목록으로 교체합니다.")
    public ApiResponse<List<ZoneResponse>> replace(
            @AuthenticationPrincipal CustomUserDetails principal,
            @PathVariable Long mapId,
            @Valid @RequestBody ZoneBatchCreateRequest request) {
        return ApiResponse.success(
                "지도 구역을 교체했습니다.",
                zoneService.replaceAll(principal.getApartmentComplexId(), mapId, request));
    }

    @GetMapping
    @Operation(summary = "지도 구역 목록 조회", description = "지도에 저장된 전체 구역을 생성 순서대로 조회합니다.")
    public ApiResponse<List<ZoneResponse>> findAll(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable Long mapId) {
        return ApiResponse.success(
                zoneService.findAll(principal.getApartmentComplexId(), mapId));
    }
}
