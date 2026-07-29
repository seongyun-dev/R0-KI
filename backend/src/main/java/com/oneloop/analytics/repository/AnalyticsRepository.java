package com.oneloop.analytics.repository;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
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
     * overview / trend 등 분석 API 공통으로 쓰는 원본 이벤트 목록 조회.
     *
     * <p>적용 조건:
     * - 단지: event.robot.apartmentComplex.id
     * - 기간: occurredAt이 from 이상, to 이하
     * - 유형/로봇/처리상태: hasXxx=true일 때만 IN 조건 적용
     *
     * <p>구역(zone) 필터는 여기서 하지 않는다.
     * 이벤트에 zoneId가 없고 좌표만 있어서, 서비스에서 CheckpointLocator로 후처리한다.
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
              AND (:hasStatuses = false OR event.processingStatus IN :statuses)
            """)
    List<DetectedEvent> findEventsForAnalytics(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("from") LocalDateTime from,
            @Param("to") LocalDateTime to,
            @Param("hasEventTypes") boolean hasEventTypes,
            @Param("eventTypes") List<EventType> eventTypes,
            @Param("hasRobotIds") boolean hasRobotIds,
            @Param("robotIds") List<Long> robotIds,
            @Param("hasStatuses") boolean hasStatuses,
            @Param("statuses") List<ProcessingStatus> statuses);
}
