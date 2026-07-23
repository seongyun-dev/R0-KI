package com.oneloop.resident.repository;

import com.oneloop.resident.domain.RegisteredVehicle;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RegisteredVehicleRepository extends JpaRepository<RegisteredVehicle, Long> {
    Optional<RegisteredVehicle> findByLicensePlate(String licensePlate);
}
