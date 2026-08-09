package com.oneloop.resident.dto.response;

import com.oneloop.resident.domain.RegisteredVehicle;
import com.oneloop.resident.domain.Resident;
import com.oneloop.resident.util.PhoneNumberMasker;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "입주민 목록 조회 응답")
public class ResidentListResponse {

    @Schema(description = "입주민 ID", example = "1")
    private Long residentId;

    @Schema(description = "입주민 이름", example = "김입주")
    private String name;

    @Schema(description = "연락처 (목록에서는 마스킹된 값)", example = "010-****-5678")
    private String maskedPhoneNumber;

    @Schema(description = "동", example = "101")
    private String buildingNumber;

    @Schema(description = "호수", example = "1502")
    private String unitNumber;

    @Schema(description = "등록 차량 수", example = "2")
    private int vehicleCount;

    @Schema(description = "대표 차량 번호 (등록 차량이 없으면 null)", example = "12가3456", nullable = true)
    private String representativeLicensePlate;

    @Schema(description = "알림 수신 여부", example = "true")
    private boolean notificationEnabled;

    @Schema(
            description = "마지막 알림 발송 시각 (발송 이력이 없으면 null)",
            example = "2026-07-30T09:12:03",
            nullable = true)
    private LocalDateTime lastNotifiedAt;

    public static ResidentListResponse of(
            Resident resident, List<RegisteredVehicle> vehicles, LocalDateTime lastNotifiedAt) {
        return ResidentListResponse.builder()
                .residentId(resident.getId())
                .name(resident.getName())
                .maskedPhoneNumber(PhoneNumberMasker.mask(resident.getPhoneNumber()))
                .buildingNumber(resident.getBuildingNumber())
                .unitNumber(resident.getUnitNumber())
                .vehicleCount(vehicles.size())
                .representativeLicensePlate(
                        vehicles.isEmpty() ? null : vehicles.get(0).getLicensePlate())
                .notificationEnabled(resident.isNotificationEnabled())
                .lastNotifiedAt(lastNotifiedAt)
                .build();
    }
}
