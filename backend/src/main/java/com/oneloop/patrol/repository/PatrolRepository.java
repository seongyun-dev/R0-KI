package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.Patrol;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PatrolRepository extends JpaRepository<Patrol, Long> {
    Page<Patrol> findAllByRobotIdOrderByStartedAtDesc(Long robotId, Pageable pageable);

    List<Patrol> findAllByRobotIdAndStartedAtGreaterThanEqual(Long robotId, LocalDateTime since);

    Optional<Patrol> findByIdAndRobotApartmentComplexId(Long id, Long apartmentComplexId);
}
