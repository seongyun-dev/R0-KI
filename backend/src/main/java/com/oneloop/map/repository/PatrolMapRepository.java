package com.oneloop.map.repository;

import com.oneloop.map.domain.PatrolMap;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PatrolMapRepository extends JpaRepository<PatrolMap, Long> {
    Optional<PatrolMap> findByApartmentComplexId(Long apartmentComplexId);

    Optional<PatrolMap> findByIdAndApartmentComplexId(Long id, Long apartmentComplexId);

    Optional<PatrolMap> findByUrlAndApartmentComplexId(String url, Long apartmentComplexId);
}
