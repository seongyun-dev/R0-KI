package com.oneloop.robot.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 수정 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RobotUpdateRequest {

    @Schema(description = "로봇 이름", example = "순찰로봇 1호", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "로봇 이름은 필수입니다.")
    @Size(max = 100, message = "로봇 이름은 100자 이하여야 합니다.")
    private String name;
}
