package com.oneloop.patrol.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰 시작 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PatrolStartRequest {

    @Schema(description = "순찰 시작할 로봇 ID", example = "1", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "로봇 ID는 필수입니다.")
    private Long robotId;
}
