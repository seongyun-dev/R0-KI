package com.oneloop.notification.service;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.response.PageResponse;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.dto.response.NotificationDetailResponse;
import com.oneloop.notification.dto.response.NotificationListResponse;
import com.oneloop.notification.event.NotificationRequestedEvent;
import com.oneloop.notification.repository.NotificationRepository;
import com.oneloop.resident.domain.Resident;
import java.util.List;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 불법주차 SMS 알림 발송 요청, 알림 조회를 담당한다.
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class NotificationService {

    private final NotificationRepository notificationRepository;
    private final ApplicationEventPublisher eventPublisher;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final CheckpointLocator checkpointLocator;

    // 불법주차 이벤트가 생성되면 등록 차주에게 SMS 발송을 요청한다.
    // EventCreationService의 트랜잭션 안에서 호출되므로, 여기서는 PENDING 저장 + 이벤트 발행까지만 하고
    // 실제 solapi 호출은 트랜잭션 커밋 후 별도 스레드(NotificationWorker)가 처리한다.
    @Transactional
    public void requestIllegalParkingNotification(DetectedEvent event, Resident recipient) {
        if (!recipient.isNotificationEnabled()) {
            return;
        }

        String content = buildContent(recipient, event);
        Notification notification =
                notificationRepository.save(new Notification(event, recipient, content));

        eventPublisher.publishEvent(
                new NotificationRequestedEvent(
                        notification.getId(), recipient.getPhoneNumber(), content));
    }

    /**
     * 로그인한 관리자의 소속 단지 알림을 전체 이력으로 조회한다.
     */
    public PageResponse<NotificationListResponse> findAll(Long apartmentComplexId, Pageable pageable) {
        Page<Notification> notifications =
                notificationRepository.findAllByRecipientApartmentComplexIdOrderByIdDesc(
                        apartmentComplexId, pageable);
        return PageResponse.from(notifications.map(NotificationListResponse::of));
    }

    /**
     * 로그인한 관리자의 소속 단지 알림 하나를 상세 조회한다.
     */
    public NotificationDetailResponse findDetail(Long apartmentComplexId, Long notificationId) {
        Notification notification =
                notificationRepository
                        .findByIdAndRecipientApartmentComplexId(notificationId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.NOTIFICATION_NOT_FOUND));

        String location = findCheckpointName(notification.getEvent(), apartmentComplexId);
        return NotificationDetailResponse.of(notification, location);
    }

    // 발송할 SMS 본문을 조립한다
    private String buildContent(Resident recipient, DetectedEvent event) {
        return """
            [한바퀴]
            %s동 %s호 차주님, 안녕하세요.
            차량(%s)이 지정 주차구역 외 장소에 주차된 것이 확인되었습니다.
            이동 부탁드립니다."""
                .formatted(
                        recipient.getBuildingNumber(),
                        recipient.getUnitNumber(),
                        event.getRecognizedLicensePlate());
    }

    // 단지의 순찰 지도에 속한 체크포인트 중 이벤트 좌표가 속한 체크포인트 이름을 찾는다.
    private String findCheckpointName(DetectedEvent event, Long apartmentComplexId) {
        Optional<PatrolMap> patrolMap = patrolMapRepository.findByApartmentComplexId(apartmentComplexId);
        List<Checkpoint> checkpoints =
                patrolMap
                        .map(map -> checkpointRepository.findAllByPatrolMapId(map.getId()))
                        .orElseGet(List::of);
        return checkpointLocator.resolveLocationName(checkpoints, event.getX(), event.getY());
    }
}
