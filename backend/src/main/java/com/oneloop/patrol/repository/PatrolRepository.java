package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.Patrol;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PatrolRepository extends JpaRepository<Patrol, Long> {}
