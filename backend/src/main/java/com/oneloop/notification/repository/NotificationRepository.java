package com.oneloop.notification.repository;

import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.domain.NotificationStatus;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface NotificationRepository extends JpaRepository<Notification, Long> {
    List<Notification> findAllByRecipientIdAndStatus(Long residentId, NotificationStatus status);

    // 알림 목록 조회 - 로그인한 관리자 소속 단지로 스코핑, event/recipient를 fetch join해 N+1 방지
    @EntityGraph(attributePaths = {"event", "recipient"})
    Page<Notification> findAllByRecipientApartmentComplexIdOrderByIdDesc(
            Long apartmentComplexId, Pageable pageable);

    // 알림 상세 조회
    Optional<Notification> findByIdAndRecipientApartmentComplexId(Long id, Long apartmentComplexId);

    // 입주민 상세 - 그 입주민에게 보낸 알림 이력을 최신순으로 조회한다
    @EntityGraph(attributePaths = "event")
    Page<Notification> findAllByRecipientIdAndRecipientApartmentComplexIdOrderByIdDesc(
            Long residentId, Long apartmentComplexId, Pageable pageable);

    // 입주민 목록 - 세대별 마지막 발송 시각을 IN 쿼리 하나로 모아 N+1을 피한다
    @Query(
            """
            SELECT notification.recipient.id AS residentId, MAX(notification.sentAt) AS lastSentAt
            FROM Notification notification
            WHERE notification.recipient.id IN :residentIds
              AND notification.status = com.oneloop.notification.domain.NotificationStatus.SENT
            GROUP BY notification.recipient.id
            """)
    List<ResidentLastNotificationProjection> findLastSentAtByResidentIds(
            @Param("residentIds") Collection<Long> residentIds);
}
