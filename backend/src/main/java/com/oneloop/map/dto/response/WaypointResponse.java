package com.oneloop.map.dto.response;

import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import java.math.BigDecimal;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class WaypointResponse {

    private Long waypointId;
    private Integer sequence;
    private BigDecimal x;
    private BigDecimal y;
    private NavigationWaypointAction action;
    private BigDecimal yaw;
    private BigDecimal acceptanceRadius;
    private Long zoneId;

    public static WaypointResponse from(NavigationWaypoint waypoint) {
        return WaypointResponse.builder()
                .waypointId(waypoint.getId())
                .sequence(waypoint.getSequence())
                .x(waypoint.getX())
                .y(waypoint.getY())
                .action(waypoint.getAction())
                .yaw(waypoint.getYaw())
                .acceptanceRadius(waypoint.getAcceptanceRadius())
                .zoneId(waypoint.getZone() == null ? null : waypoint.getZone().getId())
                .build();
    }
}
