package com.oneloop.notification.repository;

import java.time.LocalDateTime;

/** 입주민 목록에서 세대별 "마지막 알림 발송 시각"을 한 번의 그룹 쿼리로 받아오기 위한 프로젝션. */
public interface ResidentLastNotificationProjection {
    Long getResidentId();

    LocalDateTime getLastSentAt();
}
