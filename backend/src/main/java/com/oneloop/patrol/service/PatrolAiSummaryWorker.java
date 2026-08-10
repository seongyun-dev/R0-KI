package com.oneloop.patrol.service;

import com.oneloop.global.gms.client.GmsClient;
import com.oneloop.patrol.dto.internal.PatrolSummaryInput;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Slf4j
@Component
@RequiredArgsConstructor
public class PatrolAiSummaryWorker {

    private final PatrolAiSummaryStatusService statusService;
    private final GmsClient gmsClient;
    private final ObjectMapper objectMapper;

    public void generate(Long patrolId) {
        try {
            PatrolSummaryInput input = statusService.prepareGeneration(patrolId).orElse(null);
            if (input == null) {
                log.info("이미 생성 중이거나 완료된 AI 요약 작업을 건너뜁니다. patrolId={}", patrolId);
                return;
            }

            /*
             * PROCESSING 상태 저장 트랜잭션이 끝난 다음 GMS를 호출한다. 외부 API 응답을 기다리는 시간에는
             * DB 트랜잭션을 열어 두지 않으며, 응답을 받은 뒤 별도 트랜잭션으로 결과를 저장한다.
             */
            String patrolDataJson = toJson(input);
            String summaryContent = gmsClient.summarize(patrolDataJson);
            statusService.completeGeneration(patrolId, summaryContent);
        } catch (Exception exception) {
            log.error("순찰 AI 요약 생성에 실패했습니다. patrolId={}", patrolId, exception);
            statusService.failGeneration(patrolId);
        }
    }

    private String toJson(PatrolSummaryInput input) throws JacksonException {
        return objectMapper.writeValueAsString(input);
    }
}
