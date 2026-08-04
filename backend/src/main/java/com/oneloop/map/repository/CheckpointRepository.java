package com.oneloop.map.repository;

import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CheckpointRepository extends JpaRepository<Checkpoint, Long> {
    List<Checkpoint> findAllByPatrolMapId(Long mapId);

    List<Checkpoint> findAllByPatrolMapIdOrderByIdAsc(Long mapId);

    long countByPatrolMapIdAndType(Long mapId, CheckpointType type);
}
