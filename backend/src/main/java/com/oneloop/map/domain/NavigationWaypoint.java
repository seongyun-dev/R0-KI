package com.oneloop.map.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.math.BigDecimal;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
        name = "navigation_waypoints",
        uniqueConstraints =
                @UniqueConstraint(
                        name = "uk_navigation_waypoints_map_version_sequence",
                        columnNames = {"map_id", "map_version", "waypoint_sequence"}))
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class NavigationWaypoint extends BaseEntity {

    public static final BigDecimal DEFAULT_ACCEPTANCE_RADIUS = new BigDecimal("0.300");

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "waypoint_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "map_id", nullable = false)
    private PatrolMap patrolMap;

    @Column(name = "map_version", nullable = false)
    private Integer mapVersion;

    @Column(name = "waypoint_sequence", nullable = false)
    private Integer sequence;

    @Column(name = "x_coordinate", nullable = false, precision = 10, scale = 3)
    private BigDecimal x;

    @Column(name = "y_coordinate", nullable = false, precision = 10, scale = 3)
    private BigDecimal y;

    @Enumerated(EnumType.STRING)
    @Column(name = "action", nullable = false, length = 20)
    private NavigationWaypointAction action;

    @Column(name = "yaw", precision = 7, scale = 4)
    private BigDecimal yaw;

    @Column(name = "acceptance_radius", nullable = false, precision = 5, scale = 3)
    private BigDecimal acceptanceRadius;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "zone_id")
    private Checkpoint zone;

    public NavigationWaypoint(
            PatrolMap patrolMap,
            Integer mapVersion,
            Integer sequence,
            BigDecimal x,
            BigDecimal y,
            NavigationWaypointAction action,
            BigDecimal yaw,
            BigDecimal acceptanceRadius,
            Checkpoint zone) {
        this.patrolMap = patrolMap;
        this.mapVersion = mapVersion;
        this.sequence = sequence;
        this.x = x;
        this.y = y;
        this.action = action;
        this.yaw = yaw;
        this.acceptanceRadius =
                acceptanceRadius == null ? DEFAULT_ACCEPTANCE_RADIUS : acceptanceRadius;
        this.zone = zone;
    }
}
