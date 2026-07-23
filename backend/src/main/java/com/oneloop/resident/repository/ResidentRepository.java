package com.oneloop.resident.repository;

import com.oneloop.resident.domain.Resident;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ResidentRepository extends JpaRepository<Resident, Long> {}
