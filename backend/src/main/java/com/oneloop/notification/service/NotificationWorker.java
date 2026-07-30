package com.oneloop.notification.service;

import com.oneloop.global.sms.client.SmsClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

// 실제 SMS 발송(외부 API 호출)과 그 결과 기록을 담당한다.
@Slf4j
@Component
@RequiredArgsConstructor
public class NotificationWorker {

    private final SmsClient smsClient;
    private final NotificationStatusService notificationStatusService;

    // SMS를 발송하고 성공/실패에 따라 알림 상태를 갱신한다
    public void send(Long notificationId, String phoneNumber, String content) {
        try {
            smsClient.send(phoneNumber, content);
            notificationStatusService.markAsSent(notificationId);
        } catch (Exception exception) {
            log.error("SMS 발송에 실패했습니다. notificationId={}", notificationId, exception);
            notificationStatusService.markAsFailed(notificationId);
        }
    }
}
