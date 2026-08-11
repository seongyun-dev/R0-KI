package com.oneloop.map.repository;

import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CheckpointRepository extends JpaRepository<Checkpoint, Long> {
    @Query(
            """
            SELECT checkpoint
            FROM Checkpoint checkpoint
            WHERE checkpoint.patrolMap.id = :mapId
              AND checkpoint.active = true
            """)
    List<Checkpoint> findAllByPatrolMapId(@Param("mapId") Long mapId);

    @Query(
            """
            SELECT checkpoint
            FROM Checkpoint checkpoint
            WHERE checkpoint.patrolMap.id = :mapId
              AND checkpoint.active = true
            ORDER BY checkpoint.id ASC
            """)
    List<Checkpoint> findAllByPatrolMapIdOrderByIdAsc(@Param("mapId") Long mapId);

    @Query(
            """
            SELECT COUNT(checkpoint)
            FROM Checkpoint checkpoint
            WHERE checkpoint.patrolMap.id = :mapId
              AND checkpoint.type = :type
              AND checkpoint.active = true
            """)
    long countByPatrolMapIdAndType(@Param("mapId") Long mapId, @Param("type") CheckpointType type);

    @Query(
            """
            SELECT checkpoint
            FROM Checkpoint checkpoint
            WHERE checkpoint.patrolMap.id = :mapId
              AND checkpoint.id IN :checkpointIds
              AND checkpoint.active = true
            """)
    List<Checkpoint> findAllActiveByPatrolMapIdAndIdIn(
            @Param("mapId") Long mapId, @Param("checkpointIds") List<Long> checkpointIds);

    @Modifying(flushAutomatically = true)
    @Query(
            """
            UPDATE Checkpoint checkpoint
            SET checkpoint.active = false
            WHERE checkpoint.patrolMap.id = :mapId
              AND checkpoint.active = true
            """)
    int deactivateAllByPatrolMapId(@Param("mapId") Long mapId);

    @Modifying(flushAutomatically = true)
    @Query("DELETE FROM Checkpoint checkpoint WHERE checkpoint.patrolMap.id = :mapId")
    int deleteAllByPatrolMapId(@Param("mapId") Long mapId);
}
