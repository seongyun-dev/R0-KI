package com.oneloop.resident.repository;

import com.oneloop.resident.domain.RegisteredVehicle;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RegisteredVehicleRepository extends JpaRepository<RegisteredVehicle, Long> {
    Optional<RegisteredVehicle> findByLicensePlate(String licensePlate);

    boolean existsByLicensePlate(String licensePlate);

    List<RegisteredVehicle> findAllByResidentIdOrderByIdAsc(Long residentId);

    // 목록 화면에서 입주민별 차량을 한 번의 IN 쿼리로 모아 N+1을 피한다
    List<RegisteredVehicle> findAllByResidentIdInOrderByIdAsc(Collection<Long> residentIds);

    Optional<RegisteredVehicle> findByIdAndResidentId(Long id, Long residentId);
}
