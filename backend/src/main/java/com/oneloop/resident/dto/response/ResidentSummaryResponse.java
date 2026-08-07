package com.oneloop.resident.dto.response;

import com.oneloop.resident.domain.Resident;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

/** 등록·수정·알림 설정 변경 결과로 돌려주는 입주민 요약. */
@Getter
@Builder
@Schema(description = "입주민 요약 응답")
public class ResidentSummaryResponse {

    @Schema(description = "입주민 ID", example = "1")
    private Long residentId;

    @Schema(description = "입주민 이름", example = "김입주")
    private String name;

    @Schema(description = "연락처", example = "010-1234-5678")
    private String phoneNumber;

    @Schema(description = "동", example = "101")
    private String buildingNumber;

    @Schema(description = "호수", example = "1502")
    private String unitNumber;

    @Schema(description = "알림 수신 여부", example = "true")
    private boolean notificationEnabled;

    @Schema(description = "최종 수정 시각", example = "2026-08-07T10:22:11")
    private LocalDateTime updatedAt;

    public static ResidentSummaryResponse from(Resident resident) {
        return ResidentSummaryResponse.builder()
                .residentId(resident.getId())
                .name(resident.getName())
                .phoneNumber(resident.getPhoneNumber())
                .buildingNumber(resident.getBuildingNumber())
                .unitNumber(resident.getUnitNumber())
                .notificationEnabled(resident.isNotificationEnabled())
                .updatedAt(resident.getUpdatedAt())
                .build();
    }
}
