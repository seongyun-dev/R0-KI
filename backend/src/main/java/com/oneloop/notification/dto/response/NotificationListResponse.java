package com.oneloop.notification.dto.response;

import com.oneloop.event.domain.EventType;
import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.domain.NotificationStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "알림 목록 조회 응답")
public class NotificationListResponse {
    @Schema(description = "알림 ID", example = "1")
    private Long notificationId;

    @Schema(description = "연결된 이벤트 ID", example = "501")
    private Long eventId;

    @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
    private EventType eventType;

    @Schema(description = "차주 이름", example = "김입주")
    private String recipientName;

    @Schema(description = "차주 동", example = "101")
    private String buildingNumber;

    @Schema(description = "차주 호수", example = "1502")
    private String unitNumber;

    @Schema(description = "발송 상태", example = "SENT")
    private NotificationStatus status;

    @Schema(description = "발송 완료 시각 (PENDING/FAILED면 null)", example = "2026-07-30T09:12:03", nullable = true)
    private LocalDateTime sentAt;

    public static NotificationListResponse of(Notification notification) {
        return NotificationListResponse.builder()
                .notificationId(notification.getId())
                .eventId(notification.getEvent().getId())
                .eventType(notification.getEvent().getType())
                .recipientName(notification.getRecipient().getName())
                .buildingNumber(notification.getRecipient().getBuildingNumber())
                .unitNumber(notification.getRecipient().getUnitNumber())
                .status(notification.getStatus())
                .sentAt(notification.getSentAt())
                .build();
    }
}
