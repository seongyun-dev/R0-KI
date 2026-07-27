package com.oneloop.event.controller;

import com.oneloop.event.dto.request.EventBatchCreateRequest;
import com.oneloop.event.dto.request.EventCreateRequest;
import com.oneloop.event.dto.request.VehicleCheckRequest;
import com.oneloop.event.dto.response.EventBatchCreateResponse;
import com.oneloop.event.dto.response.EventCreateResponse;
import com.oneloop.event.dto.response.VehicleCheckResponse;
import com.oneloop.event.service.EventCreationService;
import com.oneloop.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

// 로봇이 서비스 토큰으로 호출하는 이벤트 생성 파이프라인 전용 컨트롤러.
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/robot")
public class RobotEventController {

    private final EventCreationService eventCreationService;

    @Operation(summary = "이벤트 생성(응급상황)", description = "로봇이 감지한 응급상황 이벤트를 생성합니다. 로봇의 가장 최근 순찰에 귀속됩니다.")
    @PostMapping("/events")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<EventCreateResponse> createEvent(
            @AuthenticationPrincipal Long robotId, @Valid @RequestBody EventCreateRequest request) {
        return ApiResponse.success(
                "이벤트가 등록되었습니다.", eventCreationService.createEvent(robotId, request));
    }

    @Operation(
            summary = "이벤트 일괄 생성(쓰레기탐지·분리수거장포화)",
            description = "순찰 종료 시점에 로봇이 감지한 이벤트를 한 번에 생성합니다. 로봇의 가장 최근 순찰에 귀속됩니다.")
    @PostMapping("/events/batch")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<EventBatchCreateResponse> createEventsBatch(
            @AuthenticationPrincipal Long robotId,
            @Valid @RequestBody EventBatchCreateRequest request) {
        return ApiResponse.success(
                "이벤트가 일괄 등록되었습니다.", eventCreationService.createEventsBatch(robotId, request));
    }

    @Operation(
            summary = "차량 판별(불법주차·미등록차량)",
            description = "순찰 종료 시점에 감지된 차량을 판별해 위반 차량만 이벤트로 생성합니다. 로봇의 가장 최근 순찰에 귀속됩니다.")
    @PostMapping("/vehicle-checks")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<VehicleCheckResponse> checkVehicles(
            @AuthenticationPrincipal Long robotId, @Valid @RequestBody VehicleCheckRequest request) {
        return ApiResponse.success(
                "차량 판별이 완료되었습니다.", eventCreationService.checkVehicles(robotId, request));
    }
}
