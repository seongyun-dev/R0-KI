package com.oneloop.robot.service;

import com.oneloop.robot.dto.response.RobotLocationResponse;
import com.oneloop.robot.dto.response.RobotStatusUpdateResponse;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Slf4j
@Service
public class RobotLocationSseService {

    private static final long SSE_TIMEOUT_MILLIS = 30 * 60 * 1000L;
    private static final String CONNECTED_EVENT = "connected";
    private static final String LOCATION_UPDATED_EVENT = "robot-location-updated";
    private static final String STATUS_UPDATED_EVENT = "robot-status-updated";

    /** 한 단지의 변경사항이 다른 단지로 전달되지 않도록 단지 ID별로 연결을 분리해서 보관합니다. */
    private final ConcurrentHashMap<Long, Set<SseEmitter>> emitters = new ConcurrentHashMap<>();

    public SseEmitter subscribe(Long apartmentComplexId) {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MILLIS);
        emitters.computeIfAbsent(apartmentComplexId, ignored -> ConcurrentHashMap.newKeySet())
                .add(emitter);

        emitter.onCompletion(() -> remove(apartmentComplexId, emitter));
        emitter.onTimeout(() -> remove(apartmentComplexId, emitter));
        emitter.onError(exception -> remove(apartmentComplexId, emitter));

        // 최초 위치와 경로는 REST로 조회하고, 여기서는 SSE 연결 수립 여부만 즉시 알려줍니다.
        send(apartmentComplexId, emitter, CONNECTED_EVENT, "connected");
        return emitter;
    }

    public void broadcastLocation(Long apartmentComplexId, RobotLocationResponse response) {
        broadcast(apartmentComplexId, LOCATION_UPDATED_EVENT, response);
    }

    public void broadcastStatus(Long apartmentComplexId, RobotStatusUpdateResponse response) {
        broadcast(apartmentComplexId, STATUS_UPDATED_EVENT, response);
    }

    private void broadcast(Long apartmentComplexId, String eventName, Object response) {
        Set<SseEmitter> complexEmitters = emitters.get(apartmentComplexId);
        if (complexEmitters == null || complexEmitters.isEmpty()) {
            return;
        }

        Set.copyOf(complexEmitters)
                .forEach(
                        emitter -> send(apartmentComplexId, emitter, eventName, response));
    }

    private void send(Long apartmentComplexId, SseEmitter emitter, String eventName, Object data) {
        try {
            emitter.send(SseEmitter.event().name(eventName).data(data));
        } catch (IOException | IllegalStateException exception) {
            log.debug(
                    "로봇 갱신 SSE 전송 실패로 연결을 제거합니다. apartmentComplexId={}",
                    apartmentComplexId,
                    exception);
            remove(apartmentComplexId, emitter);
            emitter.complete();
        }
    }

    private void remove(Long apartmentComplexId, SseEmitter emitter) {
        Set<SseEmitter> complexEmitters = emitters.get(apartmentComplexId);
        if (complexEmitters == null) {
            return;
        }

        complexEmitters.remove(emitter);
        if (complexEmitters.isEmpty()) {
            emitters.remove(apartmentComplexId, complexEmitters);
        }
    }
}
