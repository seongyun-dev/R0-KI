package com.oneloop.map.repository;

import com.oneloop.map.domain.MapStatus;
import com.oneloop.map.domain.PatrolMap;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PatrolMapRepository extends JpaRepository<PatrolMap, Long> {

    /**
     * 단지에서 현재 운영에 쓰는 active 맵 한 건.
     * 이름에 Active 가 없어도 호출부가 많으므로 의미를 active 조회로 고정한다.
     */
    @Query(
            """
            SELECT patrolMap
            FROM PatrolMap patrolMap
            WHERE patrolMap.apartmentComplex.id = :apartmentComplexId
              AND patrolMap.status = com.oneloop.map.domain.MapStatus.ACTIVE
            """)
    Optional<PatrolMap> findByApartmentComplexId(
            @Param("apartmentComplexId") Long apartmentComplexId);

    Optional<PatrolMap> findByIdAndApartmentComplexId(Long id, Long apartmentComplexId);

    List<PatrolMap> findAllByApartmentComplexIdOrderByIdDesc(Long apartmentComplexId);

    Optional<PatrolMap> findByIdAndApartmentComplexIdAndStatus(
            Long id, Long apartmentComplexId, MapStatus status);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
            """
            SELECT patrolMap
            FROM PatrolMap patrolMap
            WHERE patrolMap.apartmentComplex.id = :apartmentComplexId
              AND patrolMap.status = com.oneloop.map.domain.MapStatus.ACTIVE
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
