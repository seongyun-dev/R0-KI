package com.oneloop.analytics.service;

import com.oneloop.analytics.domain.AnalyticsAiInsight;
import com.oneloop.analytics.domain.AnalyticsInsightGenerationStatus;
import com.oneloop.analytics.dto.internal.AnalyticsInsightSnapshot;
import com.oneloop.analytics.repository.AnalyticsAiInsightRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * AI 인사이트 생성 상태/표 스냅샷 준비.
 *
 * <p>통짜 analytics DTO JSON 대신 {@link AnalyticsInsightTableBuilder}가 만든
 * 마크다운 표만 LLM에 전달한다.
 */
@Service
@RequiredArgsConstructor
public class AnalyticsInsightStatusService {

    private final AnalyticsAiInsightRepository insightRepository;
    private final AnalyticsInsightTableBuilder tableBuilder;

    /**
     * PROCESSING으로 바꾸고 GMS에 넣을 표 스냅샷을 만든다.
     *
     * @return 이미 PROCESSING/COMPLETED면 empty (중복 생성 방지)
     */
    @Transactional
    public Optional<AnalyticsInsightSnapshot> prepareGeneration(Long insightId) {
        AnalyticsAiInsight insight = findInsight(insightId);

        if (insight.getGenerationStatus() == AnalyticsInsightGenerationStatus.PROCESSING
                || insight.getGenerationStatus() == AnalyticsInsightGenerationStatus.COMPLETED) {
            return Optional.empty();
        }

        insight.startGeneration();

        Long apartmentComplexId = insight.getApartmentComplex().getId();
        String tablesMarkdown =
                tableBuilder.buildTablesMarkdown(
                        apartmentComplexId,
                        insight.getPeriodType().name(),
                        insight.getPeriodKey(),
                        insight.getPeriodFrom(),
                        insight.getPeriodTo());

        return Optional.of(
                AnalyticsInsightSnapshot.builder()
                        .periodType(insight.getPeriodType().name())
                        .periodKey(insight.getPeriodKey())
                        .periodFrom(insight.getPeriodFrom())
                        .periodTo(insight.getPeriodTo())
                        .timezone("Asia/Seoul")
                        .tablesMarkdown(tablesMarkdown)
                        .build());
    }

    @Transactional
    public void completeGeneration(Long insightId, String insightContent) {
        findInsight(insightId).completeGeneration(insightContent);
    }

    @Transactional
    public void failGeneration(Long insightId) {
        insightRepository.findById(insightId).ifPresent(AnalyticsAiInsight::failGeneration);
    }

    private AnalyticsAiInsight findInsight(Long insightId) {
        return insightRepository
                .findById(insightId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND));
    }
}
