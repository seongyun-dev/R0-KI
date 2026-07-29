package com.oneloop.analytics.repository;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * 이벤트 분석(통계) 전용 Repository.
 *
 * <p>왜 DetectedEventRepository와 분리했나:
 * - DetectedEventRepository: 이벤트 목록/상세 같은 일반 조회
 * - AnalyticsRepository: 대시보드 집계용 조회만 모음
 * 통계 쿼리가 늘어도 일반 이벤트 코드를 오염시키지 않기 위함이다. (팀 B안)
 *
 * <p>기반 테이블은 동일하다. (detected_events)
 * JpaRepository&lt;DetectedEvent, Long&gt;를 쓰므로 Spring Data JPA 스타일을 유지한다.
 */
public interface AnalyticsRepository extends JpaRepository<DetectedEvent, Long> {

    /**
     * overview 집계에 쓸 원본 이벤트 목록을 조회한다.
     *
     * <p>적용 조건:
     * - 단지: event.robot.apartmentComplex.id (반드시 로그인 단지와 일치)
     * - 기간: occurredAt이 from 이상, to 이하
     * - 유형: hasEventTypes=true일 때만 event.type IN :eventTypes
     * - 로봇: hasRobotIds=true일 때만 event.robot.id IN :robotIds
     *
     * <p>구역(zone) 필터는 여기서 하지 않는다.
     * 이벤트에 zoneId가 없고 좌표만 있어서, 서비스에서 CheckpointLocator로 후처리한다.
     *
     * <p>hasXxx 플래그가 필요한 이유:
     * `(:list IS NULL OR x IN :list)` 패턴은 Hibernate에서 List→Enum 캐스팅 오류가 난다.
     * 필터가 있을 때만 IN을 타도록 boolean으로 분기한다.
     */
    @Query(
            """
            SELECT event
            FROM DetectedEvent event
            WHERE event.robot.apartmentComplex.id = :apartmentComplexId
              AND event.occurredAt >= :from
              AND event.occurredAt <= :to
              AND (:hasEventTypes = false OR event.type IN :eventTypes)
              AND (:hasRobotIds = false OR event.robot.id IN :robotIds)
            """)
    List<DetectedEvent> findEventsForOverview(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("from") LocalDateTime from,
            @Param("to") LocalDateTime to,
            @Param("hasEventTypes") boolean hasEventTypes,
            @Param("eventTypes") List<EventType> eventTypes,
            @Param("hasRobotIds") boolean hasRobotIds,
            @Param("robotIds") List<Long> robotIds);
}
