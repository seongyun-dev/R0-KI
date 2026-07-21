package com.oneloop.robot.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 등록 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class RobotRegisterRequest {

    @Schema(description = "로봇 이름", example = "순찰로봇 1호", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "로봇 이름은 필수입니다.")
    @Size(max = 100, message = "로봇 이름은 100자 이하여야 합니다.")
    private String name;

    @Schema(
            description = "로봇 시리얼 번호",
            example = "ROBOT-0001",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "시리얼 번호는 필수입니다.")
    @Size(max = 100, message = "시리얼 번호는 100자 이하여야 합니다.")
    private String serialNumber;
}
