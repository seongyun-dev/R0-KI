package com.oneloop.map.repository;

import com.oneloop.map.domain.PatrolMap;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PatrolMapRepository extends JpaRepository<PatrolMap, Long> {
    Optional<PatrolMap> findByApartmentComplexId(Long apartmentComplexId);

    Optional<PatrolMap> findByIdAndApartmentComplexId(Long id, Long apartmentComplexId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
            """
            SELECT patrolMap
            FROM PatrolMap patrolMap
            WHERE patrolMap.apartmentComplex.id = :apartmentComplexId
            """)
    Optional<PatrolMap> findForUpdateByApartmentComplexId(
            @Param("apartmentComplexId") Long apartmentComplexId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
            """
            SELECT patrolMap
            FROM PatrolMap patrolMap
            WHERE patrolMap.id = :mapId
              AND patrolMap.apartmentComplex.id = :apartmentComplexId
            """)
    Optional<PatrolMap> findForUpdateByIdAndApartmentComplexId(
            @Param("mapId") Long mapId,
            @Param("apartmentComplexId") Long apartmentComplexId);

    Optional<PatrolMap> findByUrlAndApartmentComplexId(String url, Long apartmentComplexId);
}
