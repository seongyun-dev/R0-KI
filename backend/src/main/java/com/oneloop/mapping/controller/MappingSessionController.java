package com.oneloop.mapping.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.mapping.dto.request.MappingStartRequest;
import com.oneloop.mapping.dto.response.MappingStartResponse;
import com.oneloop.mapping.service.MappingSessionService;
import com.oneloop.mapping.service.MappingSseService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/map/mapping-sessions")
public class MappingSessionController {

    private final MappingSessionService mappingSessionService;
    private final MappingSseService mappingSseService;

    @Operation(summary = "지도 생성 시작", description = "지정한 로봇에 지도 생성 시작 명령을 전송합니다.")
    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ApiResponse<MappingStartResponse> start(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Valid @RequestBody MappingStartRequest request) {
        return ApiResponse.success(
                "지도 생성이 요청되었습니다.",
                mappingSessionService.start(principal.getApartmentComplexId(), request));
    }

    @Operation(
            summary = "지도 생성 상태 구독",
            description = "지도 생성 세션의 현재 상태와 이후 변경 상태를 SSE로 전달합니다.")
    @GetMapping(value = "/{mappingSessionId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter subscribe(
            @AuthenticationPrincipal CustomUserDetails principal,
            @PathVariable Long mappingSessionId) {
        return mappingSseService.subscribe(principal.getApartmentComplexId(), mappingSessionId);
    }
}
