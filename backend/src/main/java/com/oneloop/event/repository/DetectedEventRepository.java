package com.oneloop.event.repository;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DetectedEventRepository extends JpaRepository<DetectedEvent, Long> {
    boolean existsByPatrolIdAndTypeAndProcessingStatusNot(
            Long patrolId, EventType type, ProcessingStatus processingStatus);

    // 특정 순찰의 감지 이벤트 목록 - 순찰 상세 타임라인에 사용
    @EntityGraph(attributePaths = {"patrol.map"})
    List<DetectedEvent> findAllByPatrolIdOrderByOccurredAt(Long patrolId);

    // 이벤트 상세조회 - 로그인한 관리자 소속 단지의 이벤트인지 함께 확인
    @EntityGraph(attributePaths = {"robot", "patrol.map"})
    Optional<DetectedEvent> findByIdAndRobotApartmentComplexId(Long id, Long apartmentComplexId);

    // 증거자료 업로드 - 호출한 로봇이 그 이벤트의 담당 로봇인지 함께 확인
    Optional<DetectedEvent> findByIdAndRobotId(Long id, Long robotId);

    // 단지/유형/상태/기간으로 필터링한 이벤트 목록. robot은 fetch join으로 같이 가져와 N+1 방지
    @EntityGraph(attributePaths = {"robot", "patrol.map"})
    @Query(
            """
            SELECT event
            FROM DetectedEvent event
            WHERE event.robot.apartmentComplex.id = :apartmentComplexId
              AND (:type IS NULL OR event.type = :type)
              AND (:status IS NULL OR event.processingStatus = :status)
              AND (:fromAt IS NULL OR event.occurredAt >= :fromAt)
              AND (:toAt IS NULL OR event.occurredAt < :toAt)
            """)
    Page<DetectedEvent> findAllByFilter(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("type") EventType type,
            @Param("status") ProcessingStatus status,
            @Param("fromAt") LocalDateTime fromAt,
            @Param("toAt") LocalDateTime toAt,
            Pageable pageable);

    // 입주민 상세의 위반 이력 요약 - 해당 입주민 등록 차량 번호로 잡힌 이벤트 수를 센다
    @Query(
            """
            SELECT COUNT(event)
            FROM DetectedEvent event
            WHERE event.robot.apartmentComplex.id = :apartmentComplexId
              AND event.recognizedLicensePlate IN :licensePlates
            """)
    long countByApartmentComplexIdAndLicensePlateIn(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("licensePlates") Collection<String> licensePlates);
}
