package com.oneloop.notification.event;

import com.oneloop.notification.service.NotificationWorker;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;


@Component
@RequiredArgsConstructor
public class NotificationRequestedEventListener {

    private final NotificationWorker notificationWorker;

    // 알림 저장 트랜잭션이 커밋된 뒤에만, 별도 스레드에서 SMS 발송 워커를 실행한다.
    @Async("notificationExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(NotificationRequestedEvent event) {
        notificationWorker.send(event.notificationId(), event.phoneNumber(), event.content());
    }
}
