package com.oneloop.resident.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "입주민 알림 수신 설정 변경 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ResidentNotificationUpdateRequest {

    @Schema(
            description = "알림 수신 여부. false면 불법주차 감지 시 SMS를 보내지 않는다.",
            example = "true",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "알림 수신 여부는 필수입니다.")
    private Boolean notificationEnabled;
}
