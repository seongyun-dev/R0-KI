package com.oneloop.resident.repository;

import com.oneloop.resident.domain.Resident;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ResidentRepository extends JpaRepository<Resident, Long> {

    // 입주민 상세/수정 - 로그인한 관리자 소속 단지로 스코핑해 다른 단지 입주민 접근을 막는다
    Optional<Resident> findByIdAndApartmentComplexId(Long id, Long apartmentComplexId);

    // 등록 시 중복 판별 - DB의 uk_residents_unit_phone(단지+동+호수+연락처)과 같은 기준
    boolean existsByApartmentComplexIdAndBuildingNumberAndUnitNumberAndPhoneNumber(
            Long apartmentComplexId, String buildingNumber, String unitNumber, String phoneNumber);

    // 수정 시 중복 판별 - 자기 자신은 제외한다
    boolean existsByApartmentComplexIdAndBuildingNumberAndUnitNumberAndPhoneNumberAndIdNot(
            Long apartmentComplexId,
            String buildingNumber,
            String unitNumber,
            String phoneNumber,
            Long id);

    // 목록 필터 UI에 채울 동 목록
    @Query(
            """
            SELECT DISTINCT resident.buildingNumber
            FROM Resident resident
            WHERE resident.apartmentComplex.id = :apartmentComplexId
            ORDER BY resident.buildingNumber
            """)
    List<String> findDistinctBuildingNumbers(@Param("apartmentComplexId") Long apartmentComplexId);

    /**
     * 입주민 목록 조회.
     *
     * <p>검색어(keyword)는 이름·연락처뿐 아니라 차량번호로도 찾을 수 있어야 한다. 현장에서는 번호판을 보고 세대를 역추적하는 흐름이 가장 잦기 때문이다. 그래서
     * RegisteredVehicle을 LEFT JOIN 하고, 차량이 여러 대인 입주민이 중복 행으로 나오지 않도록 DISTINCT 로 묶는다.
     */
    @Query(
            value =
                    """
                    SELECT DISTINCT resident
                    FROM Resident resident
                    LEFT JOIN RegisteredVehicle vehicle ON vehicle.resident = resident
                    WHERE resident.apartmentComplex.id = :apartmentComplexId
                      AND (:keyword IS NULL
                           OR resident.name LIKE CONCAT('%', :keyword, '%')
                           OR resident.phoneNumber LIKE CONCAT('%', :keyword, '%')
                           OR vehicle.licensePlate LIKE CONCAT('%', :keyword, '%'))
                      AND (:buildingNumber IS NULL OR resident.buildingNumber = :buildingNumber)
                      AND (:notificationEnabled IS NULL
                           OR resident.notificationEnabled = :notificationEnabled)
                    """,
            countQuery =
                    """
                    SELECT COUNT(DISTINCT resident)
                    FROM Resident resident
                    LEFT JOIN RegisteredVehicle vehicle ON vehicle.resident = resident
                    WHERE resident.apartmentComplex.id = :apartmentComplexId
                      AND (:keyword IS NULL
                           OR resident.name LIKE CONCAT('%', :keyword, '%')
                           OR resident.phoneNumber LIKE CONCAT('%', :keyword, '%')
                           OR vehicle.licensePlate LIKE CONCAT('%', :keyword, '%'))
                      AND (:buildingNumber IS NULL OR resident.buildingNumber = :buildingNumber)
                      AND (:notificationEnabled IS NULL
                           OR resident.notificationEnabled = :notificationEnabled)
                    """)
    Page<Resident> findAllByFilter(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("keyword") String keyword,
            @Param("buildingNumber") String buildingNumber,
            @Param("notificationEnabled") Boolean notificationEnabled,
            Pageable pageable);
}
