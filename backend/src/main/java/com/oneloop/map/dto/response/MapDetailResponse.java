package com.oneloop.map.dto.response;

import com.oneloop.map.domain.PatrolMap;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "순찰 지도 상세 응답")
@Getter
@Builder
public class MapDetailResponse {

    private Long mapId;
    private String mapName;
    private String mapUrl;
    private BigDecimal resolution;
    private BigDecimal originX;
    private BigDecimal originY;
    private BigDecimal originYaw;
    private Integer width;
    private Integer height;
    private Integer mapVersion;

    public static MapDetailResponse from(PatrolMap patrolMap) {
        return MapDetailResponse.builder()
                .mapId(patrolMap.getId())
                .mapName(patrolMap.getName())
                .mapUrl(patrolMap.getUrl())
                .resolution(patrolMap.getResolution())
                .originX(patrolMap.getOriginX())
                .originY(patrolMap.getOriginY())
                .originYaw(patrolMap.getOriginYaw())
                .width(patrolMap.getWidth())
                .height(patrolMap.getHeight())
                .mapVersion(patrolMap.getMapVersion())
                .build();
    }
}
