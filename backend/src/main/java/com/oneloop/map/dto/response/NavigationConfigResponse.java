package com.oneloop.map.dto.response;

import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.PatrolMap;
import java.math.BigDecimal;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class NavigationConfigResponse {

    private int schemaVersion;
    private MapMetadataResponse map;
    private List<ZoneResponse> zones;
    private List<WaypointResponse> waypoints;

    public static NavigationConfigResponse of(
            PatrolMap patrolMap, List<ZoneResponse> zones, List<NavigationWaypoint> waypoints) {
        return NavigationConfigResponse.builder()
                .schemaVersion(1)
                .map(MapMetadataResponse.from(patrolMap))
                .zones(zones)
                .waypoints(waypoints.stream().map(WaypointResponse::from).toList())
                .build();
    }

    @Getter
    @Builder
    public static class MapMetadataResponse {

        private Long mapId;
        private Integer mapVersion;
        private String mapName;
        private BigDecimal resolution;
        private BigDecimal originX;
        private BigDecimal originY;
        private BigDecimal originYaw;
        private Integer width;
        private Integer height;

        public static MapMetadataResponse from(PatrolMap patrolMap) {
            return MapMetadataResponse.builder()
                    .mapId(patrolMap.getId())
                    .mapVersion(patrolMap.getMapVersion())
                    .mapName(patrolMap.getName())
                    .resolution(patrolMap.getResolution())
                    .originX(patrolMap.getOriginX())
                    .originY(patrolMap.getOriginY())
                    .originYaw(patrolMap.getOriginYaw())
                    .width(patrolMap.getWidth())
                    .height(patrolMap.getHeight())
                    .build();
        }
    }
}
