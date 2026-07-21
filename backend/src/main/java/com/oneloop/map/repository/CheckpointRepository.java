package com.oneloop.map.repository;

import com.oneloop.map.domain.Checkpoint;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CheckpointRepository extends JpaRepository<Checkpoint, Long> {
    List<Checkpoint> findAllByPatrolMapId(Long mapId);
}
