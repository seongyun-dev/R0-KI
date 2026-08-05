package com.oneloop.map.repository;

import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface NavigationWaypointRepository extends JpaRepository<NavigationWaypoint, Long> {

    List<NavigationWaypoint> findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
            Long mapId, Integer mapVersion);

    long countByPatrolMapIdAndMapVersionAndAction(
            Long mapId, Integer mapVersion, NavigationWaypointAction action);

    @Modifying(flushAutomatically = true)
    @Query("DELETE FROM NavigationWaypoint waypoint WHERE waypoint.patrolMap.id = :mapId")
    int deleteAllByPatrolMapId(@Param("mapId") Long mapId);

    @Modifying(flushAutomatically = true)
    @Query(
            """
            DELETE FROM NavigationWaypoint waypoint
            WHERE waypoint.patrolMap.id = :mapId
              AND waypoint.mapVersion = :mapVersion
            """)
    int deleteAllByPatrolMapIdAndMapVersion(
            @Param("mapId") Long mapId, @Param("mapVersion") Integer mapVersion);
}
