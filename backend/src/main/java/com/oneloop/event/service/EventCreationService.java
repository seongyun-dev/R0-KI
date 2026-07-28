package com.oneloop.event.service;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventEvidence;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.RiskLevel;
import com.oneloop.event.dto.request.EventBatchCreateRequest;
import com.oneloop.event.dto.request.EventBatchItemRequest;
import com.oneloop.event.dto.request.EventCreateRequest;
import com.oneloop.event.dto.request.EvidenceUploadRequest;
import com.oneloop.event.dto.request.VehicleCheckItemRequest;
import com.oneloop.event.dto.request.VehicleCheckRequest;
import com.oneloop.event.dto.response.EventBatchCreateResponse;
import com.oneloop.event.dto.response.EventBatchCreatedItem;
import com.oneloop.event.dto.response.EventCreateResponse;
import com.oneloop.event.dto.response.EvidenceUploadResponse;
import com.oneloop.event.dto.response.VehicleCheckResponse;
import com.oneloop.event.dto.response.VehicleViolationResponse;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.event.repository.EventEvidenceRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.file.FileStorageService;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.resident.domain.RegisteredVehicle;
import com.oneloop.resident.repository.RegisteredVehicleRepository;
import com.oneloop.robot.domain.PatrolRobot;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 로봇이 REST로 호출하는 이벤트 생성 파이프라인(응급상황 단건/쓰레기탐지 일괄/차량판별) 전용 서비스.
@Service
@RequiredArgsConstructor
@Transactional
public class EventCreationService {

    private static final Pattern CONFIDENCE_PATTERN = Pattern.compile("confidence=([0-9]*\\.?[0-9]+)");

    private final DetectedEventRepository detectedEventRepository;
    private final EventEvidenceRepository eventEvidenceRepository;
    private final PatrolRepository patrolRepository;
    private final RegisteredVehicleRepository registeredVehicleRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final CheckpointLocator checkpointLocator;
    private final FileStorageService fileStorageService;

    /**
     * 로봇이 응급상황을 감지했을 때 호출하는 단건 이벤트 생성.
     */
    public EventCreateResponse createEvent(Long robotId, EventCreateRequest request) {
        Patrol patrol =
                patrolRepository
                        .findFirstByRobotIdOrderByStartedAtDesc(robotId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.PATROL_NOT_FOUND));
        PatrolRobot robot = patrol.getRobot();

        DetectedEvent event =
                saveEvent(
                        patrol,
                        robot,
                        request.getEventType(),
                        request.getEventTitle(),
                        request.getEventDetails(),
                        parseConfidence(request.getEventDetails()),
                        request.getOccurredAt().toLocalDateTime(),
                        request.getX(),
                        request.getY(),
                        request.getRiskLevel(),
                        request.getRecognizedLicensePlate());
        patrol.increaseDetectedEventCount();

        return EventCreateResponse.of(event.getId());
    }

    /**
     * 로봇이 순찰 종료 시점에 쓰레기탐지·분리수거장포화 이벤트를 한 번에 전송할 때 호출하는 일괄 생성.
     * 요청 배열의 tempId를 응답에 그대로 실어 보내 로봇이 각 이벤트의 eventId를 매칭할 수 있게 한다.
     */
    public EventBatchCreateResponse createEventsBatch(Long robotId, EventBatchCreateRequest request) {
        Patrol patrol =
                patrolRepository
                        .findFirstByRobotIdOrderByStartedAtDesc(robotId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.PATROL_NOT_FOUND));
        PatrolRobot robot = patrol.getRobot();

        List<EventBatchCreatedItem> createdItems =
                request.getEvents().stream()
                        .map(item -> createBatchItem(patrol, robot, item))
                        .toList();

        return EventBatchCreateResponse.of(createdItems);
    }

    private EventBatchCreatedItem createBatchItem(
            Patrol patrol, PatrolRobot robot, EventBatchItemRequest item) {
        DetectedEvent event =
                saveEvent(
                        patrol,
                        robot,
                        item.getEventType(),
                        item.getEventTitle(),
                        item.getEventDetails(),
                        parseConfidence(item.getEventDetails()),
                        item.getOccurredAt().toLocalDateTime(),
                        item.getX(),
                        item.getY(),
                        item.getRiskLevel(),
                        null);
        patrol.increaseDetectedEventCount();
        return EventBatchCreatedItem.of(item.getTempId(), event.getId());
    }

    /**
     * 로봇이 순찰 종료 시점에 감지한 차량들을 일괄 판별한다. 우선순위: 미등록차량 > 불법주차, 차량 1대당 이벤트 최대 1건.
     * 위반 없는 차량은 이벤트를 만들지 않고 응답에도 포함하지 않는다.
     */
    public VehicleCheckResponse checkVehicles(Long robotId, VehicleCheckRequest request) {
        Patrol patrol =
                patrolRepository
                        .findFirstByRobotIdOrderByStartedAtDesc(robotId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.PATROL_NOT_FOUND));
        PatrolRobot robot = patrol.getRobot();
        List<Checkpoint> parkingCheckpoints =
                findParkingCheckpoints(robot.getApartmentComplex().getId());

        List<VehicleViolationResponse> violations =
                request.getVehicles().stream()
                        .map(vehicle -> checkVehicle(patrol, robot, vehicle, parkingCheckpoints))
                        .filter(Objects::nonNull)
                        .toList();

        return VehicleCheckResponse.of(violations);
    }

    // 차량 1대를 판별해 위반이면 이벤트를 생성하고 응답 항목을 반환, 위반이 아니면 null
    private VehicleViolationResponse checkVehicle(
            Patrol patrol, PatrolRobot robot, VehicleCheckItemRequest vehicle, List<Checkpoint> parkingCheckpoints) {
        Optional<RegisteredVehicle> registeredVehicle =
                registeredVehicleRepository.findByLicensePlate(vehicle.getLicensePlate());

        EventType violationType;
        if (registeredVehicle.isEmpty()) {
            violationType = EventType.UNREGISTERED_VEHICLE;
        } else if (checkpointLocator
                .findContaining(parkingCheckpoints, vehicle.getX(), vehicle.getY())
                .isEmpty()) {
            violationType = EventType.ILLEGAL_PARKING;
        } else {
            return null;
        }

        DetectedEvent event =
                saveEvent(
                        patrol,
                        robot,
                        violationType,
                        resolveVehicleEventTitle(violationType),
                        vehicle.getEventDetails(),
                        parseConfidence(vehicle.getEventDetails()),
                        vehicle.getOccurredAt().toLocalDateTime(),
                        vehicle.getX(),
                        vehicle.getY(),
                        RiskLevel.NORMAL,
                        vehicle.getLicensePlate());
        patrol.increaseDetectedEventCount();

        return VehicleViolationResponse.of(vehicle.getTempId(), event.getId());
    }

    /**
     * 로봇이 이벤트에 대한 증거자료(사진)를 업로드한다.
     */
    public EvidenceUploadResponse uploadEvidence(Long robotId, Long eventId, EvidenceUploadRequest request) {
        // 호출한 로봇이 그 이벤트의 담당 로봇인지 확인 후 파일을 저장한다.
        DetectedEvent event =
                detectedEventRepository
                        .findByIdAndRobotId(eventId, robotId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.EVENT_NOT_FOUND));

        String fileUrl = fileStorageService.store(request.getFile());
        LocalDateTime capturedAt =
                request.getCapturedAt() != null
                        ? request.getCapturedAt().toLocalDateTime()
                        : LocalDateTime.now();
        EventEvidence evidence = new EventEvidence(event, request.getMediaType(), fileUrl, capturedAt);
        eventEvidenceRepository.save(evidence);

        return EvidenceUploadResponse.of(evidence.getId());
    }

    private String resolveVehicleEventTitle(EventType type) {
        return switch (type) {
            case UNREGISTERED_VEHICLE -> "미등록 차량 감지";
            case ILLEGAL_PARKING -> "불법주차 감지";
            default -> throw new IllegalStateException("차량 판별에서 나올 수 없는 이벤트 유형: " + type);
        };
    }

    // 단지의 순찰 지도에 속한 체크포인트 중 PARKING 타입만 가져온다. 지도가 없으면 빈 목록
    private List<Checkpoint> findParkingCheckpoints(Long apartmentComplexId) {
        Optional<PatrolMap> patrolMap = patrolMapRepository.findByApartmentComplexId(apartmentComplexId);
        return patrolMap
                .map(map -> checkpointRepository.findAllByPatrolMapId(map.getId()))
                .orElseGet(List::of)
                .stream()
                .filter(checkpoint -> checkpoint.getType() == CheckpointType.PARKING)
                .toList();
    }

    // 이벤트 저장 공통 로직.
    private DetectedEvent saveEvent(
            Patrol patrol,
            PatrolRobot robot,
            EventType type,
            String title,
            String details,
            BigDecimal confidence,
            LocalDateTime occurredAt,
            BigDecimal x,
            BigDecimal y,
            RiskLevel riskLevel,
            String recognizedLicensePlate) {
        DetectedEvent event =
                new DetectedEvent(
                        patrol,
                        robot,
                        type,
                        title,
                        details,
                        confidence,
                        occurredAt,
                        x,
                        y,
                        riskLevel,
                        recognizedLicensePlate);
        return detectedEventRepository.save(event);
    }

    // eventDetails 원본 텍스트에서 "confidence=0.94" 같은 패턴을 찾아 값만 파싱. 없으면 null
    private BigDecimal parseConfidence(String eventDetails) {
        if (eventDetails == null) {
            return null;
        }
        Matcher matcher = CONFIDENCE_PATTERN.matcher(eventDetails);
        return matcher.find() ? new BigDecimal(matcher.group(1)) : null;
    }
}
