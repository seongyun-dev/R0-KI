package com.oneloop.resident.controller;

import static org.springframework.data.domain.Sort.Direction.DESC;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.response.PageResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.resident.dto.request.ResidentNotificationUpdateRequest;
import com.oneloop.resident.dto.request.ResidentRegisterRequest;
import com.oneloop.resident.dto.request.ResidentUpdateRequest;
import com.oneloop.resident.dto.request.VehicleRegisterRequest;
import com.oneloop.resident.dto.response.RegisteredVehicleResponse;
import com.oneloop.resident.dto.response.ResidentDetailResponse;
import com.oneloop.resident.dto.response.ResidentFilterOptionsResponse;
import com.oneloop.resident.dto.response.ResidentListResponse;
import com.oneloop.resident.dto.response.ResidentNotificationHistoryResponse;
import com.oneloop.resident.dto.response.ResidentSummaryResponse;
import com.oneloop.resident.service.ResidentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/residents")
public class ResidentController {

    private final ResidentService residentService;

    @Operation(summary = "입주민 등록", description = "소속 단지에 입주민을 등록합니다. 차량을 함께 등록할 수 있습니다.")
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<ResidentSummaryResponse> register(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Valid @RequestBody ResidentRegisterRequest request) {
        return ApiResponse.success(
                "입주민이 등록되었습니다.",
                residentService.register(principal.getApartmentComplexId(), request));
    }

    @Operation(
            summary = "입주민 목록 조회",
            description = "소속 단지의 입주민을 조회합니다. 검색어는 이름·연락처·차량번호에 부분 일치합니다.")
    @GetMapping
    public ApiResponse<PageResponse<ResidentListResponse>> list(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "이름·연락처·차량번호 검색어", example = "12가3456")
                    @RequestParam(required = false)
                    String keyword,
            @Parameter(description = "동 필터", example = "101") @RequestParam(required = false)
                    String buildingNumber,
            @Parameter(description = "알림 수신 여부 필터", example = "true")
                    @RequestParam(required = false)
                    Boolean notificationEnabled,
            @ParameterObject
                    @PageableDefault(
                            size = 20,
                            sort = {"buildingNumber", "unitNumber"})
                    Pageable pageable) {
        return ApiResponse.success(
                residentService.findAll(
                        principal.getApartmentComplexId(),
                        keyword,
                        buildingNumber,
                        notificationEnabled,
                        pageable));
    }

    @Operation(summary = "입주민 목록 필터 옵션 조회", description = "목록 화면의 동 필터에 채울 값을 조회합니다.")
    @GetMapping("/filter-options")
    public ApiResponse<ResidentFilterOptionsResponse> filterOptions(
            @AuthenticationPrincipal CustomUserDetails principal) {
        return ApiResponse.success(
                residentService.findFilterOptions(principal.getApartmentComplexId()));
    }

    @Operation(summary = "입주민 상세 조회", description = "입주민 하나를 등록 차량·알림 이력 미리보기·위반 이력 요약과 함께 조회합니다.")
    @GetMapping("/{residentId}")
    public ApiResponse<ResidentDetailResponse> detail(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "입주민 ID", example = "1", required = true) @PathVariable
                    Long residentId) {
        return ApiResponse.success(
                residentService.findDetail(principal.getApartmentComplexId(), residentId));
    }

    @Operation(summary = "입주민 알림 이력 조회", description = "해당 입주민에게 발송된 알림 이력을 최신순으로 조회합니다.")
    @GetMapping("/{residentId}/notifications")
    public ApiResponse<PageResponse<ResidentNotificationHistoryResponse>> notifications(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "입주민 ID", example = "1", required = true) @PathVariable
                    Long residentId,
            @ParameterObject @PageableDefault(size = 20, sort = "id", direction = DESC)
                    Pageable pageable) {
        return ApiResponse.success(
                residentService.findNotifications(
                        principal.getApartmentComplexId(), residentId, pageable));
    }

    @Operation(summary = "입주민 정보 수정", description = "입주민의 이름·연락처·동·호수를 수정합니다.")
    @PatchMapping("/{residentId}")
    public ApiResponse<ResidentSummaryResponse> update(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "입주민 ID", example = "1", required = true) @PathVariable
                    Long residentId,
            @Valid @RequestBody ResidentUpdateRequest request) {
        return ApiResponse.success(
                "입주민 정보가 수정되었습니다.",
                residentService.update(principal.getApartmentComplexId(), residentId, request));
    }

    @Operation(summary = "입주민 알림 수신 설정 변경", description = "끄면 불법주차가 감지돼도 해당 입주민에게 SMS를 발송하지 않습니다.")
    @PatchMapping("/{residentId}/notification")
    public ApiResponse<ResidentSummaryResponse> changeNotificationEnabled(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "입주민 ID", example = "1", required = true) @PathVariable
                    Long residentId,
            @Valid @RequestBody ResidentNotificationUpdateRequest request) {
        return ApiResponse.success(
                "알림 수신 설정이 변경되었습니다.",
                residentService.changeNotificationEnabled(
                        principal.getApartmentComplexId(), residentId, request));
    }

    @Operation(summary = "입주민 차량 등록", description = "입주민에게 차량을 추가 등록합니다.")
    @PostMapping("/{residentId}/vehicles")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<RegisteredVehicleResponse> addVehicle(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "입주민 ID", example = "1", required = true) @PathVariable
                    Long residentId,
            @Valid @RequestBody VehicleRegisterRequest request) {
        return ApiResponse.success(
                "차량이 등록되었습니다.",
                residentService.addVehicle(principal.getApartmentComplexId(), residentId, request));
    }

    @Operation(summary = "입주민 차량 삭제", description = "입주민의 등록 차량을 삭제합니다.")
    @DeleteMapping("/{residentId}/vehicles/{vehicleId}")
    public ApiResponse<RegisteredVehicleResponse> deleteVehicle(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "입주민 ID", example = "1", required = true) @PathVariable
                    Long residentId,
            @Parameter(description = "차량 ID", example = "1", required = true) @PathVariable
                    Long vehicleId) {
        return ApiResponse.success(
                "차량이 삭제되었습니다.",
                residentService.deleteVehicle(
                        principal.getApartmentComplexId(), residentId, vehicleId));
    }
}
