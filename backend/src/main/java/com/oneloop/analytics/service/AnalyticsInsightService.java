package com.oneloop.analytics.service;

import com.oneloop.analytics.domain.AnalyticsAiInsight;
import com.oneloop.analytics.domain.AnalyticsInsightGenerationStatus;
import com.oneloop.analytics.domain.AnalyticsInsightPeriodType;
import com.oneloop.analytics.dto.response.AnalyticsInsightResponse;
import com.oneloop.analytics.event.AnalyticsInsightRequestedEvent;
import com.oneloop.analytics.repository.AnalyticsAiInsightRepository;
import com.oneloop.analytics.service.AnalyticsInsightPeriodResolver.ResolvedPeriod;
import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * AI 인사이트 조회 + lazy/스케줄 생성 트리거.
 *
 * <p>COMPLETED면 DB만 반환한다. 없거나 PENDING/FAILED면 row를 확보하고
 * 커밋 후 Worker가 GMS를 호출하도록 이벤트를 발행한다.
 */
@Service
@RequiredArgsConstructor
public class AnalyticsInsightService {

    private final AnalyticsInsightPeriodResolver periodResolver;
    private final AnalyticsAiInsightRepository insightRepository;
    private final ApartmentComplexRepository apartmentComplexRepository;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public AnalyticsInsightResponse getInsight(
            Long apartmentComplexId, AnalyticsInsightPeriodType periodType) {
        ResolvedPeriod period = periodResolver.resolve(periodType);
        AnalyticsAiInsight insight = findOrCreatePending(apartmentComplexId, period);
        requestGenerationIfNeeded(insight);
        return toResponse(insight, period);
    }

    /**
     * 스케줄러용 생성 요청.
     *
     * @return 이벤트를 발행했으면 true, COMPLETED/PROCESSING 등으로 스킵하면 false
     */
    @Transactional
    public boolean requestGeneration(
            Long apartmentComplexId, AnalyticsInsightPeriodType periodType) {
        ResolvedPeriod period = periodResolver.resolve(periodType);
        AnalyticsAiInsight insight = findOrCreatePending(apartmentComplexId, period);
        return requestGenerationIfNeeded(insight);
    }

    private boolean requestGenerationIfNeeded(AnalyticsAiInsight insight) {
        if (insight.getGenerationStatus() == AnalyticsInsightGenerationStatus.COMPLETED
                || insight.getGenerationStatus() == AnalyticsInsightGenerationStatus.PROCESSING) {
            return false;
        }

        // PENDING 또는 FAILED → 비동기 생성(재시도) 요청
        eventPublisher.publishEvent(new AnalyticsInsightRequestedEvent(insight.getId()));
        return true;
    }

    private AnalyticsAiInsight findOrCreatePending(
            Long apartmentComplexId, ResolvedPeriod period) {
        return insightRepository
                .findByApartmentComplexIdAndPeriodTypeAndPeriodKey(
                        apartmentComplexId, period.getPeriodType(), period.getPeriodKey())
                .orElseGet(() -> createPending(apartmentComplexId, period));
    }

    private AnalyticsAiInsight createPending(Long apartmentComplexId, ResolvedPeriod period) {
        ApartmentComplex apartmentComplex =
                apartmentComplexRepository
                        .findById(apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND));

        try {
            return insightRepository.save(
                    new AnalyticsAiInsight(
                            apartmentComplex,
                            period.getPeriodType(),
                            period.getPeriodKey(),
                            period.getPeriodFrom(),
                            period.getPeriodTo()));
        } catch (DataIntegrityViolationException exception) {
            // 동시 조회 시 UK 충돌 → 이미 만든 row를 다시 읽는다
            return insightRepository
                    .findByApartmentComplexIdAndPeriodTypeAndPeriodKey(
                            apartmentComplexId, period.getPeriodType(), period.getPeriodKey())
                    .orElseThrow(() -> exception);
        }
    }

    private AnalyticsInsightResponse toResponse(AnalyticsAiInsight insight, ResolvedPeriod period) {
        return AnalyticsInsightResponse.builder()
                .insightId(insight.getId())
                .periodType(insight.getPeriodType())
                .periodKey(insight.getPeriodKey())
                .periodFrom(insight.getPeriodFrom())
                .periodTo(insight.getPeriodTo())
                .timezone(period.getTimezone())
                .generationStatus(insight.getGenerationStatus())
                .insightContent(insight.getInsightContent())
                .build();
    }
}
