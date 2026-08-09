package com.oneloop.patrol.event;

import com.oneloop.patrol.service.PatrolAiSummaryWorker;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@RequiredArgsConstructor
public class PatrolCompletedEventListener {

    private final PatrolAiSummaryWorker patrolAiSummaryWorker;

    /*
     * 순찰 종료 트랜잭션이 정상 커밋된 뒤 AI 요약 전용 스레드에 작업을 전달한다.
     * @Async 덕분에 추후 연결될 MQTT 수신 스레드는 GMS 응답을 기다리지 않고 종료 처리를 마칠 수 있다.
     */
    @Async("patrolSummaryExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(PatrolCompletedEvent event) {
        patrolAiSummaryWorker.generate(event.patrolId());
    }
}
