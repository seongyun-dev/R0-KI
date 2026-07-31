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
@Schema(description = "알림 상세 조회 응답")
public class NotificationDetailResponse {
    @Schema(description = "알림 ID", example = "1")
    private Long notificationId;

    @Schema(description = "연결된 이벤트 ID", example = "501")
    private Long eventId;

    @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
    private EventType eventType;

    @Schema(description = "발송된 문자 전체 내용", example = "[한바퀴] 101동 1502호 차주님, 차량(12가3456)이 불법주차 구역에서 감지되었습니다. 확인 부탁드립니다.")
    private String content;

    @Schema(description = "차주 이름", example = "김입주")
    private String recipientName;

    @Schema(description = "차주 연락처", example = "01012345678")
    private String recipientPhoneNumber;

    @Schema(description = "차주 동", example = "101")
    private String buildingNumber;

    @Schema(description = "차주 호수", example = "1502")
    private String unitNumber;

    @Schema(description = "이벤트 탐지 시각", example = "2026-07-30T09:11:40")
    private LocalDateTime occurredAt;

    @Schema(description = "차량 번호", example = "12가3456")
    private String licensePlate;

    @Schema(description = "이벤트 발생 위치가 속한 체크포인트 이름 (매칭되는 구역이 없으면 null)", example = "주차장", nullable = true)
    private String location;

    @Schema(description = "발송 상태", example = "SENT")
    private NotificationStatus status;

    @Schema(description = "발송 완료 시각 (PENDING/FAILED면 null)", example = "2026-07-30T09:12:03", nullable = true)
    private LocalDateTime sentAt;

    public static NotificationDetailResponse of(Notification notification, String location) {
        return NotificationDetailResponse.builder()
                .notificationId(notification.getId())
                .eventId(notification.getEvent().getId())
                .eventType(notification.getEvent().getType())
                .content(notification.getContent())
                .recipientName(notification.getRecipient().getName())
                .recipientPhoneNumber(notification.getRecipient().getPhoneNumber())
                .buildingNumber(notification.getRecipient().getBuildingNumber())
                .unitNumber(notification.getRecipient().getUnitNumber())
                .occurredAt(notification.getEvent().getOccurredAt())
                .licensePlate(notification.getEvent().getRecognizedLicensePlate())
                .location(location)
                .status(notification.getStatus())
                .sentAt(notification.getSentAt())
                .build();
    }
}
