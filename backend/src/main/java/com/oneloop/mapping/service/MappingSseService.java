package com.oneloop.mapping.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.dto.response.MappingStatusEventResponse;
import com.oneloop.mapping.repository.MappingSessionRepository;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MappingSseService {

    private static final long SSE_TIMEOUT_MILLIS = 30 * 60 * 1000L;
    private static final String MAPPING_STATUS_EVENT = "mapping-status";

    private final MappingSessionRepository mappingSessionRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final ConcurrentHashMap<Long, Set<SseEmitter>> emitters = new ConcurrentHashMap<>();

    public SseEmitter subscribe(Long apartmentComplexId, Long mappingSessionId) {
        MappingSession session =
                mappingSessionRepository
                        .findByIdAndApartmentComplexId(mappingSessionId, apartmentComplexId)
                        .orElseThrow(
                                () ->
                                        new BusinessException(
                                                ErrorCode.MAPPING_SESSION_NOT_FOUND));

        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MILLIS);
        emitters.computeIfAbsent(mappingSessionId, ignored -> ConcurrentHashMap.newKeySet())
                .add(emitter);

        emitter.onCompletion(() -> remove(mappingSessionId, emitter));
        emitter.onTimeout(() -> remove(mappingSessionId, emitter));
        emitter.onError(exception -> remove(mappingSessionId, emitter));

        // ACK가 SSE 연결보다 먼저 도착한 경우에도 프론트가 최신 상태를 바로 알 수 있게 한다.
        Long mapId =
                session.getResultMap() != null
                        ? session.getResultMap().getId()
                        : patrolMapRepository
                                .findByApartmentComplexId(session.getApartmentComplex().getId())
                                .map(patrolMap -> patrolMap.getId())
                                .orElse(null);
        send(mappingSessionId, emitter, MappingStatusEventResponse.from(session, mapId));
        if (isTerminal(session.getStatus())) {
            complete(mappingSessionId, emitter);
        }
        return emitter;
    }

    public void broadcast(Long mappingSessionId, MappingStatusEventResponse response) {
        Set<SseEmitter> sessionEmitters = emitters.get(mappingSessionId);
        if (sessionEmitters == null || sessionEmitters.isEmpty()) {
            return;
        }

        Set<SseEmitter> snapshot = Set.copyOf(sessionEmitters);
        snapshot.forEach(emitter -> send(mappingSessionId, emitter, response));

        if (isTerminal(response.getStatus())) {
            completeAll(mappingSessionId);
        }
    }

    private void send(
            Long mappingSessionId,
            SseEmitter emitter,
            MappingStatusEventResponse response) {
        try {
            emitter.send(
                    SseEmitter.event()
                            .name(MAPPING_STATUS_EVENT)
                            .data(response));
        } catch (IOException | IllegalStateException exception) {
            log.debug(
                    "지도 생성 SSE 전송 실패로 연결을 제거합니다. mappingSessionId={}",
                    mappingSessionId,
                    exception);
            remove(mappingSessionId, emitter);
            emitter.complete();
        }
    }

    private void remove(Long mappingSessionId, SseEmitter emitter) {
        Set<SseEmitter> sessionEmitters = emitters.get(mappingSessionId);
        if (sessionEmitters == null) {
            return;
        }

        sessionEmitters.remove(emitter);
        if (sessionEmitters.isEmpty()) {
            emitters.remove(mappingSessionId, sessionEmitters);
        }
    }

    private void complete(Long mappingSessionId, SseEmitter emitter) {
        remove(mappingSessionId, emitter);
        emitter.complete();
    }

    private void completeAll(Long mappingSessionId) {
        Set<SseEmitter> sessionEmitters = emitters.remove(mappingSessionId);
        if (sessionEmitters != null) {
            sessionEmitters.forEach(SseEmitter::complete);
        }
    }

    private boolean isTerminal(MappingStatus status) {
        return status == MappingStatus.COMPLETED
                || status == MappingStatus.FAILED
                || status == MappingStatus.CANCELLED;
    }
}
