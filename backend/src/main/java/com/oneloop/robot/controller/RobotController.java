package com.oneloop.robot.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.response.PageResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.robot.dto.request.RobotRegisterRequest;
import com.oneloop.robot.dto.request.RobotUpdateRequest;
import com.oneloop.robot.dto.response.RobotDeleteResponse;
import com.oneloop.robot.dto.response.RobotDetailResponse;
import com.oneloop.robot.dto.response.RobotListResponse;
import com.oneloop.robot.dto.response.RobotMapLocationResponse;
import com.oneloop.robot.dto.response.RobotRegisterResponse;
import com.oneloop.robot.dto.response.RobotStatsResponse;
import com.oneloop.robot.dto.response.RobotUpdateResponse;
import com.oneloop.robot.service.RobotLocationQueryService;
import com.oneloop.robot.service.RobotLocationSseService;
import com.oneloop.robot.service.RobotService;
import com.oneloop.robot.service.RobotSseService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/robots")
public class RobotController {

    private final RobotService robotService;
    private final RobotSseService robotSseService;
    private final RobotLocationSseService robotLocationSseService;
    private final RobotLocationQueryService robotLocationQueryService;

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

    @Operation(
            summary = "순찰 중 로봇 위치 조회",
            description = "대시보드 최초 표시에 필요한 순찰 중 로봇의 최신 위치와 현재 순찰 경로를 조회합니다.")
    @GetMapping("/locations")
    public ApiResponse<List<RobotMapLocationResponse>> locations(
            @AuthenticationPrincipal CustomUserDetails principal) {
        return ApiResponse.success(
                robotLocationQueryService.findPatrollingLocations(
                        principal.getApartmentComplexId()));
    }

    @Operation(
            summary = "로봇 최신 위치 조회",
            description = "선택한 로봇의 최신 위치를 조회하며, 순찰 중이면 현재 순찰 경로도 함께 반환합니다.")
    @GetMapping("/{robotId}/location")
    public ApiResponse<RobotMapLocationResponse> location(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable Long robotId) {
        return ApiResponse.success(
                robotLocationQueryService.findRobotLocation(
                        principal.getApartmentComplexId(), robotId));
    }

    @Operation(summary = "로봇 상세 조회", description = "순찰로봇 하나를 상세 조회합니다.")
    @GetMapping("/{robotId}")
    public ApiResponse<RobotDetailResponse> detail(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable Long robotId) {
        return ApiResponse.success(robotService.findById(principal.getApartmentComplexId(), robotId));
    }

    @Operation(summary = "로봇 수정", description = "순찰로봇의 이름을 수정합니다.")
    @PatchMapping("/{robotId}")
    public ApiResponse<RobotUpdateResponse> update(
            @AuthenticationPrincipal CustomUserDetails principal,
            @PathVariable Long robotId,
            @Valid @RequestBody RobotUpdateRequest request) {
        return ApiResponse.success(
                "로봇 정보가 수정되었습니다.",
                robotService.update(principal.getApartmentComplexId(), robotId, request));
    }

    @Operation(summary = "로봇 삭제", description = "순찰로봇을 삭제합니다.")
    @DeleteMapping("/{robotId}")
    public ApiResponse<RobotDeleteResponse> delete(
            @AuthenticationPrincipal CustomUserDetails principal, @PathVariable Long robotId) {
        return ApiResponse.success(
                "로봇이 삭제되었습니다.",
                robotService.delete(principal.getApartmentComplexId(), robotId));
    }

    @Operation(summary = "로봇 장애물 이벤트 구독", description = "로그인한 관리자 단지의 로봇 장애물 감지/해제 이벤트를 SSE로 구독합니다.")
    @GetMapping(value = "/obstacle-events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter subscribeObstacleEvents(@AuthenticationPrincipal CustomUserDetails principal) {
        return robotSseService.subscribe(principal.getApartmentComplexId());
    }

    @Operation(
            summary = "로봇 위치·상태 이벤트 구독",
            description = "로그인한 관리자 단지 로봇의 실시간 위치와 상태 변경 이벤트를 SSE로 구독합니다.")
    @GetMapping(value = "/location/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter subscribeLocationEvents(
            @AuthenticationPrincipal CustomUserDetails principal) {
        return robotLocationSseService.subscribe(principal.getApartmentComplexId());
    }
}
