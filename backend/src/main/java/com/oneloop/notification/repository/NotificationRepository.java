package com.oneloop.notification.repository;

import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.domain.NotificationStatus;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NotificationRepository extends JpaRepository<Notification, Long> {
    List<Notification> findAllByRecipientIdAndStatus(Long residentId, NotificationStatus status);
}
