package com.oneloop.analytics.event;

import com.oneloop.analytics.service.AnalyticsInsightWorker;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 인사이트 생성 이벤트 리스너.
 *
 * <p>조회 API 트랜잭션이 커밋된 뒤 전용 스레드에서 Worker를 실행한다.
 * API 응답은 GMS를 기다리지 않고 PENDING/PROCESSING 상태로 바로 반환된다.
 */
@Component
@RequiredArgsConstructor
public class AnalyticsInsightRequestedEventListener {

    private final AnalyticsInsightWorker analyticsInsightWorker;

    @Async("analyticsInsightExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(AnalyticsInsightRequestedEvent event) {
        analyticsInsightWorker.generate(event.insightId());
    }
}
