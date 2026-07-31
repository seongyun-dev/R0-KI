package com.oneloop.notification.repository;

import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.domain.NotificationStatus;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NotificationRepository extends JpaRepository<Notification, Long> {
    List<Notification> findAllByRecipientIdAndStatus(Long residentId, NotificationStatus status);

    // 알림 목록 조회 - 로그인한 관리자 소속 단지로 스코핑, event/recipient를 fetch join해 N+1 방지
    @EntityGraph(attributePaths = {"event", "recipient"})
    Page<Notification> findAllByRecipientApartmentComplexIdOrderByIdDesc(
            Long apartmentComplexId, Pageable pageable);

    // 알림 상세 조회
    Optional<Notification> findByIdAndRecipientApartmentComplexId(Long id, Long apartmentComplexId);
}
