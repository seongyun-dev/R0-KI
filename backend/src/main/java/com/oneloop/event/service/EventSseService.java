package com.oneloop.event.service;

import com.oneloop.event.dto.response.EmergencyEventSseResponse;
import com.oneloop.event.dto.response.PatrolCompletedSseResponse;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Slf4j
@Service
public class EventSseService {

    private static final String CONNECTED_EVENT = "connected";
    private static final String EMERGENCY_EVENT = "emergency-event";
    private static final String PATROL_COMPLETED_EVENT = "patrol-completed";

    private final ConcurrentHashMap<Long, Set<SseEmitter>> emergencyEmitters =
            new ConcurrentHashMap<>();
    private final ConcurrentHashMap<Long, Set<SseEmitter>> generalEmitters =
            new ConcurrentHashMap<>();
    private final long timeoutMillis;

    public EventSseService(
            @Value("${app.event-sse.timeout-millis:1800000}") long timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }

    public SseEmitter subscribeEmergency(Long apartmentComplexId) {
        return subscribe(emergencyEmitters, apartmentComplexId);
    }

    public SseEmitter subscribeGeneral(Long apartmentComplexId) {
        return subscribe(generalEmitters, apartmentComplexId);
    }

    public void broadcastEmergency(Long apartmentComplexId, EmergencyEventSseResponse response) {
        log.info(
                "[EVENT_SSE] 발송 시작 channel=emergency apartmentComplexId={} eventId={} subscribers={}",
                apartmentComplexId,
                response.getEventId(),
                subscriberCount(emergencyEmitters, apartmentComplexId));
        broadcast(emergencyEmitters, apartmentComplexId, EMERGENCY_EVENT, response);
    }

    public void broadcastPatrolCompleted(
            Long apartmentComplexId, PatrolCompletedSseResponse response) {
        log.info(
                "[EVENT_SSE] 발송 시작 channel=general apartmentComplexId={} patrolId={} subscribers={}",
                apartmentComplexId,
                response.getPatrolId(),
                subscriberCount(generalEmitters, apartmentComplexId));
        broadcast(generalEmitters, apartmentComplexId, PATROL_COMPLETED_EVENT, response);
    }

    private SseEmitter subscribe(
            ConcurrentHashMap<Long, Set<SseEmitter>> emitters, Long apartmentComplexId) {
        SseEmitter emitter = new SseEmitter(timeoutMillis);
        emitters.computeIfAbsent(apartmentComplexId, ignored -> ConcurrentHashMap.newKeySet())
                .add(emitter);
        log.info(
                "[EVENT_SSE] 구독 연결 channel={} apartmentComplexId={} subscribers={}",
                channelOf(emitters),
                apartmentComplexId,
                subscriberCount(emitters, apartmentComplexId));

        emitter.onCompletion(() -> remove(emitters, apartmentComplexId, emitter));
        emitter.onTimeout(() -> remove(emitters, apartmentComplexId, emitter));
        emitter.onError(exception -> remove(emitters, apartmentComplexId, emitter));
        send(emitters, apartmentComplexId, emitter, CONNECTED_EVENT, "connected");
        return emitter;
    }

    private void broadcast(
            ConcurrentHashMap<Long, Set<SseEmitter>> emitters,
            Long apartmentComplexId,
            String eventName,
            Object data) {
        Set<SseEmitter> complexEmitters = emitters.get(apartmentComplexId);
        if (complexEmitters == null || complexEmitters.isEmpty()) {
            return;
        }

        Set.copyOf(complexEmitters)
                .forEach(emitter -> send(emitters, apartmentComplexId, emitter, eventName, data));
    }

    private void send(
            ConcurrentHashMap<Long, Set<SseEmitter>> emitters,
            Long apartmentComplexId,
            SseEmitter emitter,
            String eventName,
            Object data) {
        try {
            emitter.send(SseEmitter.event().name(eventName).data(data));
        } catch (IOException | IllegalStateException exception) {
            log.warn(
                    "[EVENT_SSE] 전송 실패 channel={} apartmentComplexId={} eventName={}",
                    channelOf(emitters),
                    apartmentComplexId,
                    eventName,
                    exception);
            remove(emitters, apartmentComplexId, emitter);
            emitter.complete();
        }
    }

    private void remove(
            ConcurrentHashMap<Long, Set<SseEmitter>> emitters,
            Long apartmentComplexId,
            SseEmitter emitter) {
        Set<SseEmitter> complexEmitters = emitters.get(apartmentComplexId);
        if (complexEmitters == null) {
            return;
        }

        if (!complexEmitters.remove(emitter)) {
            return;
        }

        log.info(
                "[EVENT_SSE] 구독 종료 channel={} apartmentComplexId={} subscribers={}",
                channelOf(emitters),
                apartmentComplexId,
                complexEmitters.size());
        if (complexEmitters.isEmpty()) {
            emitters.remove(apartmentComplexId, complexEmitters);
        }
    }

    private int subscriberCount(
            ConcurrentHashMap<Long, Set<SseEmitter>> emitters, Long apartmentComplexId) {
        Set<SseEmitter> complexEmitters = emitters.get(apartmentComplexId);
        return complexEmitters == null ? 0 : complexEmitters.size();
    }

    private String channelOf(ConcurrentHashMap<Long, Set<SseEmitter>> emitters) {
        return emitters == emergencyEmitters ? "emergency" : "general";
    }
}
