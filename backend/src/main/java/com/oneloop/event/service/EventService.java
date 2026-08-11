package com.oneloop.event.service;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventProcessingHistory;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.event.dto.request.EventPeriodFilter;
import com.oneloop.event.dto.request.EventStatusChangeRequest;
import com.oneloop.event.dto.response.EventDetailResponse;
import com.oneloop.event.dto.response.EventEvidenceResponse;
import com.oneloop.event.dto.response.EventListResponse;
import com.oneloop.event.dto.response.EventStatusChangeResponse;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.event.repository.EventEvidenceRepository;
import com.oneloop.event.repository.EventProcessingHistoryRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.response.PageResponse;
import com.oneloop.map.util.EventCheckpointResolver;
import com.oneloop.member.repository.MemberRepository;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class EventService {

    // 기간 필터(오늘/최근 7일) 계산 기준 타임존. 서버가 UTC로 떠도 KST 기준 "오늘"이 되도록 고정
    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");

    private final DetectedEventRepository detectedEventRepository;
    private final EventProcessingHistoryRepository eventProcessingHistoryRepository;
    private final EventEvidenceRepository eventEvidenceRepository;
    private final EventCheckpointResolver eventCheckpointResolver;
    private final MemberRepository memberRepository;
    private final EmergencyPatrolResumeService emergencyPatrolResumeService;

    /**
     * 로그인한 관리자의 소속 단지 이벤트를 유형·상태·기간으로 필터링하여 조회한다. 페이지에 포함된 모든 이벤트의 담당자는 한 번의 IN 쿼리로
     * 조회해 이벤트마다 개별 쿼리가 실행되는 N+1 문제를 방지한다.
     */
    public PageResponse<EventListResponse> findAll(
            Long apartmentComplexId,
            EventType type,
            ProcessingStatus status,
            EventPeriodFilter period,
            Pageable pageable) {
        DateTimeRange range = calculateRange(period);
        Page<DetectedEvent> events =
                detectedEventRepository.findAllByFilter(
                        apartmentComplexId, type, status, range.fromAt(), range.toAt(), pageable);

        // 체크포인트 목록은 단지당 1번만 조회해서 페이지 내 모든 이벤트의 위치 매칭에 재사용
        Map<Long, List<Checkpoint>> checkpointsByMap =
                eventCheckpointResolver.loadCheckpointIndex(events.getContent());
        List<Long> eventIds = events.stream().map(DetectedEvent::getId).toList();
        Map<Long, String> assigneeByEventId = findLatestAssigneeByEventId(eventIds);

        Page<EventListResponse> responses =
                events.map(
                        event ->
                                EventListResponse.of(
                                        event,
                                        eventCheckpointResolver.resolveLocationName(
                                                event, checkpointsByMap),
                                        assigneeByEventId.get(event.getId())));
        return PageResponse.from(responses);
    }

    /**
     * 로그인한 관리자의 소속 단지 이벤트 하나를 상세 조회한다.
     */
    public EventDetailResponse findDetail(Long apartmentComplexId, Long eventId) {
        // 다른 단지 소속 이벤트는 존재해도 404로 처리 (URL로 타 단지 이벤트 ID를 넣어 조회하는 것 방지)
        DetectedEvent event =
                detectedEventRepository
                        .findByIdAndRobotApartmentComplexId(eventId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.EVENT_NOT_FOUND));

        Map<Long, List<Checkpoint>> checkpointsByMap =
                eventCheckpointResolver.loadCheckpointIndex(List.of(event));
        String location = eventCheckpointResolver.resolveLocationName(event, checkpointsByMap);
        // 처리중이면 경과초, 완료됐으면 null (완료시각 자체는 event.processedAt으로 별도 노출)
        Long elapsedSeconds = calculateElapsedSeconds(event);
        // 처리완료 상태일 때만 완료 시점 처리이력의 메모를 붙임
        String processingNote = findProcessingNote(event);
        // 이벤트당 증거자료는 1건이 원칙 - 가장 최근 것 하나만 응답에 포함
        EventEvidenceResponse evidence =
                eventEvidenceRepository
                        .findFirstByEventIdOrderByCapturedAtDesc(eventId)
                        .map(EventEvidenceResponse::from)
                        .orElse(null);

        return EventDetailResponse.of(event, location, elapsedSeconds, processingNote, evidence);
    }

    /**
     * 이벤트의 처리 상태를 변경하고, 그 변경을 처리이력에 자동으로 기록한다.
     */
    @Transactional
    public EventStatusChangeResponse changeStatus(
            Long apartmentComplexId, Long memberId, Long eventId, EventStatusChangeRequest request) {
        DetectedEvent event =
                detectedEventRepository
                        .findByIdAndRobotApartmentComplexId(eventId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.EVENT_NOT_FOUND));

        event.changeStatus(request.getProcessingStatus());

        EventProcessingHistory history =
                eventProcessingHistoryRepository.save(
                        new EventProcessingHistory(
                                event,
                                memberRepository.getReferenceById(memberId),
                                request.getProcessingStatus(),
                                request.getProcessingNote()));

        if (request.getProcessingStatus() == ProcessingStatus.COMPLETED) {
            emergencyPatrolResumeService.resumeIfEligible(event);
        }

        return EventStatusChangeResponse.of(event, history.getChangedAt());
    }

    // 이벤트 ID 목록에 대한 처리이력을 한 번에 조회한 뒤, 이벤트별로 가장 최근(changedAt 최신) 담당자 이름만 뽑는다
    private Map<Long, String> findLatestAssigneeByEventId(List<Long> eventIds) {
        if (eventIds.isEmpty()) {
            return Map.of();
        }
        return eventProcessingHistoryRepository.findAllByEventIdInOrderByChangedAtDesc(eventIds).stream()
                .collect(
                        Collectors.groupingBy(
                                // 이미 changedAt 내림차순으로 정렬돼 있으므로, 그룹의 첫 원소가 가장 최근 기록
                                history -> history.getEvent().getId(),
                                Collectors.collectingAndThen(
                                        Collectors.reducing((first, second) -> first),
                                        history ->
                                                history.map(EventProcessingHistory::getProcessingMember)
                                                        .map(member -> member.getName())
                                                        .orElse(null))));
    }

    // 처리완료 전에는 탐지시각부터 지금까지의 경과시간(초)을, 완료됐으면 null을 반환한다
    private Long calculateElapsedSeconds(DetectedEvent event) {
        if (event.getProcessingStatus() == ProcessingStatus.COMPLETED) {
            return null;
        }
        return Duration.between(event.getOccurredAt(), LocalDateTime.now()).getSeconds();
    }

    // COMPLETED로 바뀐 시점의 처리이력에 남긴 메모를 찾는다. 완료 상태가 아니면 애초에 조회하지 않음
    private String findProcessingNote(DetectedEvent event) {
        if (event.getProcessingStatus() != ProcessingStatus.COMPLETED) {
            return null;
        }
        return eventProcessingHistoryRepository
                .findFirstByEventIdAndChangedStatusOrderByChangedAtDesc(
                        event.getId(), ProcessingStatus.COMPLETED)
                .map(EventProcessingHistory::getNote)
                .orElse(null);
    }

    // 기간 필터를 실제 조회 범위(fromAt~toAt)로 변환. ALL이면 범위 제한 없음
    private DateTimeRange calculateRange(EventPeriodFilter period) {
        ZonedDateTime now = ZonedDateTime.now(SERVICE_ZONE);
        return switch (period) {
            case ALL -> new DateTimeRange(null, null);
            case TODAY -> {
                LocalDate today = now.toLocalDate();
                yield new DateTimeRange(today.atStartOfDay(), today.plusDays(1).atStartOfDay());
            }
            case LAST_7_DAYS ->
                    new DateTimeRange(now.minusDays(7).toLocalDateTime(), now.toLocalDateTime());
        };
    }

    private record DateTimeRange(LocalDateTime fromAt, LocalDateTime toAt) {}
}
