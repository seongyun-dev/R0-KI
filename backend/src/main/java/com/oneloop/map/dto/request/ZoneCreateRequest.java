package com.oneloop.map.dto.request;

import com.oneloop.map.domain.CheckpointType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@Schema(description = "지도 구역 생성 요청")
public class ZoneCreateRequest {

    @NotBlank
    @Size(max = 100)
    @Schema(description = "구역 이름", example = "101동 지하 주차장")
    private String name;

    @NotNull
    @Schema(description = "구역 유형", example = "PARKING")
    private CheckpointType type;

    @NotNull
    @Schema(description = "드래그 시작점 X 좌표", example = "1.250")
    private BigDecimal startX;

    @NotNull
    @Schema(description = "드래그 시작점 Y 좌표", example = "3.500")
    private BigDecimal startY;

    @NotNull
    @Schema(description = "드래그 종료점 X 좌표", example = "8.750")
    private BigDecimal endX;

    @NotNull
    @Schema(description = "드래그 종료점 Y 좌표", example = "9.500")
    private BigDecimal endY;
}
