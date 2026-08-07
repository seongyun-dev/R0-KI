package com.oneloop.resident.dto.response;

import com.oneloop.resident.domain.RegisteredVehicle;
import com.oneloop.resident.domain.Resident;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "입주민 상세 조회 응답")
public class ResidentDetailResponse {

    @Schema(description = "입주민 ID", example = "1")
    private Long residentId;

    @Schema(description = "입주민 이름", example = "김입주")
    private String name;

    @Schema(description = "연락처 (상세에서는 전체 노출)", example = "010-1234-5678")
    private String phoneNumber;

    @Schema(description = "동", example = "101")
    private String buildingNumber;

    @Schema(description = "호수", example = "1502")
    private String unitNumber;

    @Schema(description = "알림 수신 여부", example = "true")
    private boolean notificationEnabled;

    @Schema(description = "등록 차량 목록")
    private List<RegisteredVehicleResponse> vehicles;

    @Schema(description = "이 입주민에게 발송된 알림 총 건수", example = "3")
    private long notificationCount;

    @Schema(description = "이 입주민의 등록 차량으로 감지된 이벤트 총 건수", example = "5")
    private long violationCount;

    @Schema(description = "최근 알림 이력 (최신순)")
    private List<ResidentNotificationHistoryResponse> recentNotifications;

    @Schema(description = "등록 시각", example = "2026-05-02T14:03:00")
    private LocalDateTime createdAt;

    @Schema(description = "최종 수정 시각", example = "2026-08-07T10:22:11")
    private LocalDateTime updatedAt;

    public static ResidentDetailResponse of(
            Resident resident,
            List<RegisteredVehicle> vehicles,
            long notificationCount,
            long violationCount,
            List<ResidentNotificationHistoryResponse> recentNotifications) {
        return ResidentDetailResponse.builder()
                .residentId(resident.getId())
                .name(resident.getName())
                .phoneNumber(resident.getPhoneNumber())
                .buildingNumber(resident.getBuildingNumber())
                .unitNumber(resident.getUnitNumber())
                .notificationEnabled(resident.isNotificationEnabled())
                .vehicles(vehicles.stream().map(RegisteredVehicleResponse::from).toList())
                .notificationCount(notificationCount)
                .violationCount(violationCount)
                .recentNotifications(recentNotifications)
                .createdAt(resident.getCreatedAt())
                .updatedAt(resident.getUpdatedAt())
                .build();
    }
}
