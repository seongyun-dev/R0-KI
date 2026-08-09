package com.oneloop.resident.dto.response;

import com.oneloop.event.domain.EventType;
import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.domain.NotificationStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "입주민에게 발송된 알림 이력 응답")
public class ResidentNotificationHistoryResponse {

    @Schema(description = "알림 ID", example = "1")
    private Long notificationId;

    @Schema(description = "연결된 이벤트 ID", example = "501")
    private Long eventId;

    @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
    private EventType eventType;

    @Schema(description = "발송 상태", example = "SENT")
    private NotificationStatus status;

    @Schema(
            description = "발송 완료 시각 (PENDING/FAILED면 null)",
            example = "2026-07-30T09:12:03",
            nullable = true)
    private LocalDateTime sentAt;

    @Schema(description = "알림 생성 시각", example = "2026-07-30T09:12:01")
    private LocalDateTime createdAt;

    public static ResidentNotificationHistoryResponse from(Notification notification) {
        return ResidentNotificationHistoryResponse.builder()
                .notificationId(notification.getId())
                .eventId(notification.getEvent().getId())
                .eventType(notification.getEvent().getType())
                .status(notification.getStatus())
                .sentAt(notification.getSentAt())
                .createdAt(notification.getCreatedAt())
                .build();
    }
}
