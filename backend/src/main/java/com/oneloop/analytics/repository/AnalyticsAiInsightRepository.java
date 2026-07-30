package com.oneloop.analytics.repository;

import com.oneloop.analytics.domain.AnalyticsAiInsight;
import com.oneloop.analytics.domain.AnalyticsInsightPeriodType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * AI 인사이트 캐시 Repository.
 *
 * <p>조회 키는 UK와 동일하다: 단지 + periodType + periodKey.
 * Step 2 조회 API / Step 3 Worker에서 이 메서드로 캐시 hit 여부를 판별한다.
 */
public interface AnalyticsAiInsightRepository extends JpaRepository<AnalyticsAiInsight, Long> {

    Optional<AnalyticsAiInsight> findByApartmentComplexIdAndPeriodTypeAndPeriodKey(
            Long apartmentComplexId, AnalyticsInsightPeriodType periodType, String periodKey);
}
