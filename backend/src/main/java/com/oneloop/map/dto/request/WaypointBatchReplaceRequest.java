package com.oneloop.map.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "지도 버전에 대응하는 순찰 경로 전체 교체 요청")
public class WaypointBatchReplaceRequest {

    @NotNull
    @Positive
    @Schema(description = "편집 기준 지도 버전")
    private Integer mapVersion;

    @Valid
    @NotEmpty
    @Size(max = 500)
    private List<WaypointReplaceItemRequest> waypoints;
}
