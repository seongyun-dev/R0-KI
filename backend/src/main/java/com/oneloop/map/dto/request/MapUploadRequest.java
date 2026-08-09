package com.oneloop.map.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import lombok.Getter;
import lombok.Setter;
import org.springframework.web.multipart.MultipartFile;

@Schema(description = "SLAM 지도 등록 요청")
@Getter
@Setter
public class MapUploadRequest {

    @Schema(description = "지도 생성 명령 UUID")
    @NotBlank
    private String commandId;

    @Schema(description = "브라우저에서 표시할 PNG 지도 이미지")
    @NotNull
    private MultipartFile mapImage;

    @Schema(description = "픽셀당 실제 거리(m)", example = "0.0500")
    @NotNull
    @DecimalMin(value = "0.0001")
    private BigDecimal resolution;

    @Schema(description = "지도 원점 X 좌표", example = "-10.000")
    @NotNull
    private BigDecimal originX;

    @Schema(description = "지도 원점 Y 좌표", example = "-10.000")
    @NotNull
    private BigDecimal originY;

    @Schema(description = "지도 원점 회전값(rad)", example = "0.00")
    @NotNull
    private BigDecimal originYaw;

}
