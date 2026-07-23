package com.oneloop.patrol.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.patrol.event.PatrolCompletedEvent;
import com.oneloop.patrol.repository.PatrolRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class PatrolAiSummaryService {

    private final ApplicationEventPublisher eventPublisher;
    private final PatrolRepository patrolRepository;

    /**
     * 순찰 종료 데이터가 저장된 뒤 AI 요약 생성을 요청한다.
     *
     * <p>추후 MQTT 순찰 종료 처리 트랜잭션 안에서 이 메서드를 호출한다. 실제 GMS 호출은
     * {@code PatrolCompletedEventListener}가 트랜잭션 커밋 이후 별도 스레드에서 실행하므로, MQTT 수신 스레드는 GMS 응답을 기다리지
     * 않는다.
     *
     * @param patrolId 요약을 생성할 순찰 식별자
     */
    @Transactional
    public void requestGeneration(Long patrolId) {
        if (!patrolRepository.existsById(patrolId)) {
            throw new BusinessException(ErrorCode.PATROL_NOT_FOUND);
        }
        eventPublisher.publishEvent(new PatrolCompletedEvent(patrolId));
    }

}
