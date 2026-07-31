package com.oneloop.notification.service;

import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.repository.NotificationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 알림 발송 상태 갱신 전용. NotificationWorker에서 자기 자신의 @Transactional 메서드를
// this.로 호출하면 프록시를 안 거쳐 트랜잭션이 적용되지 않으므로 별도 빈으로 분리한다.
@Service
@RequiredArgsConstructor
public class NotificationStatusService {

    private final NotificationRepository notificationRepository;

    @Transactional
    public void markAsSent(Long notificationId) {
        notificationRepository.findById(notificationId).ifPresent(Notification::markAsSent);
    }

    @Transactional
    public void markAsFailed(Long notificationId) {
        notificationRepository.findById(notificationId).ifPresent(Notification::markAsFailed);
    }
}
