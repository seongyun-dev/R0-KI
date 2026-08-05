package com.oneloop.map.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@Schema(description = "지도 구역 일괄 생성 요청")
public class ZoneBatchCreateRequest {

    @Positive
    @Schema(description = "편집 기준 지도 버전. 기존 클라이언트는 생략 가능")
    private Integer mapVersion;

    @Valid
    @NotEmpty
    @Size(max = 100)
    @Schema(description = "한 번에 생성할 구역 목록")
    private List<ZoneCreateRequest> zones;
}
