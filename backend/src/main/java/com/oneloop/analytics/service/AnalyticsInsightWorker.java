package com.oneloop.analytics.service;

import com.oneloop.analytics.dto.internal.AnalyticsInsightSnapshot;
import com.oneloop.global.gms.client.GmsClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * AI 인사이트 생성 Worker.
 *
 * <p>흐름: prepare(PROCESSING + 표 생성) → GMS 호출(트랜잭션 밖) → COMPLETED/FAILED.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AnalyticsInsightWorker {

    private final AnalyticsInsightStatusService statusService;
    private final GmsClient gmsClient;

    public void generate(Long insightId) {
        try {
            AnalyticsInsightSnapshot snapshot =
                    statusService.prepareGeneration(insightId).orElse(null);
            if (snapshot == null) {
                log.info("이미 생성 중이거나 완료된 AI 인사이트를 건너뜁니다. insightId={}", insightId);
                return;
            }

            String tablesMarkdown = snapshot.getTablesMarkdown();
            log.info(
                    "AI 인사이트 표 입력 준비 완료. insightId={}, chars={}",
                    insightId,
                    tablesMarkdown == null ? 0 : tablesMarkdown.length());

            /*
             * 표 마크다운만 넘긴다. 통짜 overview/trend JSON은 폐기했다.
             * (토큰·환각 감소, 경비원용 해석 안정화)
             */
            String insightContent = gmsClient.generateAnalyticsInsight(tablesMarkdown);
            statusService.completeGeneration(insightId, insightContent);
        } catch (Exception exception) {
            log.error("통계 AI 인사이트 생성에 실패했습니다. insightId={}", insightId, exception);
            statusService.failGeneration(insightId);
        }
    }
}
