package com.oneloop.robot.service;

import com.oneloop.robot.dto.response.RobotObstacleEventResponse;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

// 관리자 대시보드가 단지 단위로 로봇 장애물 이벤트를 구독하는 SSE 연결을 관리한다.
@Slf4j
@Service
public class RobotSseService {

    // 로봇 장애물은 지도 생성과 달리 "완료"라는 개념이 없어 연결이 계속 열려있음 - 타임아웃만 넉넉히 둠
    private static final long SSE_TIMEOUT_MILLIS = 30 * 60 * 1000L;
    private static final String ROBOT_OBSTACLE_EVENT = "robot-obstacle";

    private final ConcurrentHashMap<Long, Set<SseEmitter>> emitters = new ConcurrentHashMap<>();

    // 단지 단위로 emitter를 생성해 등록한다 - 관리자 한 명이 자기 단지의 모든 로봇을 한 연결로 지켜봄
    public SseEmitter subscribe(Long apartmentComplexId) {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MILLIS);
        emitters.computeIfAbsent(apartmentComplexId, ignored -> ConcurrentHashMap.newKeySet()).add(emitter);

        emitter.onCompletion(() -> remove(apartmentComplexId, emitter));
        emitter.onTimeout(() -> remove(apartmentComplexId, emitter));
        emitter.onError(exception -> remove(apartmentComplexId, emitter));

        return emitter;
    }

    // 해당 단지를 구독 중인 모든 연결에 이벤트를 흘려보낸다
    public void broadcast(Long apartmentComplexId, RobotObstacleEventResponse response) {
        Set<SseEmitter> complexEmitters = emitters.get(apartmentComplexId);
        if (complexEmitters == null || complexEmitters.isEmpty()) {
            return;
        }

        Set.copyOf(complexEmitters).forEach(emitter -> send(apartmentComplexId, emitter, response));
    }

    private void send(Long apartmentComplexId, SseEmitter emitter, RobotObstacleEventResponse response) {
        try {
            emitter.send(SseEmitter.event().name(ROBOT_OBSTACLE_EVENT).data(response));
        } catch (IOException | IllegalStateException exception) {
            log.debug("로봇 장애물 SSE 전송 실패로 연결을 제거합니다. apartmentComplexId={}", apartmentComplexId, exception);
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
