package com.oneloop.map.dto.response;

import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.PatrolMap;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class WaypointSetResponse {

    private Long mapId;
    private Integer mapVersion;
    private List<WaypointResponse> waypoints;

    public static WaypointSetResponse from(
            PatrolMap patrolMap, List<NavigationWaypoint> waypoints) {
        return WaypointSetResponse.builder()
                .mapId(patrolMap.getId())
                .mapVersion(patrolMap.getMapVersion())
                .waypoints(waypoints.stream().map(WaypointResponse::from).toList())
                .build();
    }
}
