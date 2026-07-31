package com.oneloop.notification.event;

// 알림이 PENDING으로 저장된 뒤, 실제 SMS 발송을 요청하기 위해 발행하는 이벤트
public record NotificationRequestedEvent(Long notificationId, String phoneNumber, String content) {}
