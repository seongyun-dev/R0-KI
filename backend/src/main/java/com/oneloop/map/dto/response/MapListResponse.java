package com.oneloop.map.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "단지 지도 목록 응답")
@Getter
@Builder
public class MapListResponse {

    private List<MapDetailResponse> maps;
    private Long activeMapId;
}
