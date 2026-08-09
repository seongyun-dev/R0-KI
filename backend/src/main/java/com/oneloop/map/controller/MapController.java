package com.oneloop.map.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.map.dto.request.MapUploadRequest;
import com.oneloop.map.dto.response.MapDetailResponse;
import com.oneloop.map.dto.response.MapUploadResponse;
import com.oneloop.map.service.MapService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/map")
public class MapController {

    private final MapService mapService;

    @Operation(
            summary = "SLAM 지도 등록",
            description = "로봇이 생성한 PNG 지도와 좌표 메타데이터를 등록하고 지도 생성 세션을 완료합니다.")
    @PostMapping(
            value = "/mapping-sessions/{mappingSessionId}/map",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<MapUploadResponse> upload(
            @PathVariable Long mappingSessionId,
            @AuthenticationPrincipal Long robotId,
            @Valid @ModelAttribute MapUploadRequest request) {
        return ApiResponse.success(
                "지도가 등록되었습니다.", mapService.upload(mappingSessionId, robotId, request));
    }

    @Operation(summary = "현재 단지 지도 조회", description = "로그인한 관리자의 단지에 등록된 현재 지도를 조회합니다.")
    @GetMapping("/current")
    public ApiResponse<MapDetailResponse> getCurrent(
            @AuthenticationPrincipal CustomUserDetails principal) {
        return ApiResponse.success(mapService.getCurrent(principal.getApartmentComplexId()));
    }

    @Operation(summary = "지도 상세 조회", description = "로그인한 관리자의 단지에 등록된 지도 정보를 조회합니다.")
    @GetMapping("/{mapId}")
    public ApiResponse<MapDetailResponse> get(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable Long mapId) {
        return ApiResponse.success(mapService.get(principal.getApartmentComplexId(), mapId));
    }

    @Operation(summary = "지도 이미지 조회", description = "로그인한 관리자의 단지에 등록된 PNG 지도 이미지를 반환합니다.")
    @GetMapping(value = "/files/{storedName:.+}", produces = MediaType.IMAGE_PNG_VALUE)
    public ResponseEntity<Resource> getFile(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable String storedName) {
        Resource resource = mapService.getFile(principal.getApartmentComplexId(), storedName);
        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_PNG)
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline")
                .body(resource);
    }
}
