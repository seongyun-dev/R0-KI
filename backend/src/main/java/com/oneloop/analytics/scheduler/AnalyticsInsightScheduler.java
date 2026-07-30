package com.oneloop.analytics.scheduler;

import com.oneloop.analytics.domain.AnalyticsInsightPeriodType;
import com.oneloop.analytics.service.AnalyticsInsightService;
import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 단지별 AI 인사이트 사전 생성 스케줄러.
 *
 * <p>매주 월요일·매월 1일에 직전 완료 주/월 인사이트를 enqueue 한다.
 * 실제 GMS 호출은 기존 Worker({@code analyticsInsightExecutor})가 담당한다.
 *
 * <p>월요일과 1일이 겹치면 cron 두 개가 각각 실행되어 WEEK·MONTH 모두 생성된다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AnalyticsInsightScheduler {

    private final ApartmentComplexRepository apartmentComplexRepository;
    private final AnalyticsInsightService analyticsInsightService;

    /** 매주 월요일 00:10 (Asia/Seoul) — 직전 주간 인사이트. */
    @Scheduled(cron = "0 10 0 * * MON", zone = "Asia/Seoul")
    public void enqueueWeeklyInsights() {
        enqueueForAllComplexes(AnalyticsInsightPeriodType.WEEK);
    }

    /** 매월 1일 00:20 (Asia/Seoul) — 직전 월간 인사이트. */
    @Scheduled(cron = "0 20 0 1 * *", zone = "Asia/Seoul")
    public void enqueueMonthlyInsights() {
        enqueueForAllComplexes(AnalyticsInsightPeriodType.MONTH);
    }

    private void enqueueForAllComplexes(AnalyticsInsightPeriodType periodType) {
        List<ApartmentComplex> complexes = apartmentComplexRepository.findAll();
        int requested = 0;
        int skipped = 0;

        log.info(
                "AI 인사이트 스케줄 시작. periodType={}, complexes={}",
                periodType,
                complexes.size());

        for (ApartmentComplex complex : complexes) {
            try {
                boolean enqueued =
                        analyticsInsightService.requestGeneration(complex.getId(), periodType);
                if (enqueued) {
                    requested++;
                } else {
                    skipped++;
                }
            } catch (Exception exception) {
                // 한 단지 실패가 나머지 단지 스케줄을 막지 않도록 한다.
                log.error(
                        "AI 인사이트 스케줄 enqueue 실패. apartmentComplexId={}, periodType={}",
                        complex.getId(),
                        periodType,
                        exception);
            }
        }

        log.info(
                "AI 인사이트 스케줄 완료. periodType={}, requested={}, skipped={}",
                periodType,
                requested,
                skipped);
    }
}
