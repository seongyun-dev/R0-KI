package com.oneloop.analytics.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 단지·기간(주/월) 단위 AI 인사이트 캐시.
 *
 * <p>테이블: {@code analytics_ai_insights} (Flyway V13)
 *
 * <p>순찰 1건 요약({@code patrol_ai_summaries})과 달리,
 * UK (apartment_complex_id, period_type, period_key)로 단지당 주/월 1건만 유지한다.
 * 화면 조회 시 COMPLETED면 DB만 반환하고, 없을 때만 Worker가 LLM을 호출한다.
 */
@Getter
@Entity
@Table(
        name = "analytics_ai_insights",
        uniqueConstraints =
                @UniqueConstraint(
                        name = "uk_analytics_ai_insights_apartment_period",
                        columnNames = {"apartment_complex_id", "period_type", "period_key"}))
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AnalyticsAiInsight extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "insight_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false)
    private ApartmentComplex apartmentComplex;

    @Enumerated(EnumType.STRING)
    @Column(name = "period_type", nullable = false, length = 10)
    private AnalyticsInsightPeriodType periodType;

    /** 기간 식별자. 예: {@code 2026-W30}, {@code 2026-07} */
    @Column(name = "period_key", nullable = false, length = 16)
    private String periodKey;

    @Column(name = "period_from", nullable = false)
    private LocalDateTime periodFrom;

    @Column(name = "period_to", nullable = false)
    private LocalDateTime periodTo;

    @Enumerated(EnumType.STRING)
    @Column(name = "generation_status", nullable = false, length = 20)
    private AnalyticsInsightGenerationStatus generationStatus =
            AnalyticsInsightGenerationStatus.PENDING;

    @Column(name = "insight_content", columnDefinition = "MEDIUMTEXT")
    private String insightContent;

    public AnalyticsAiInsight(
            ApartmentComplex apartmentComplex,
            AnalyticsInsightPeriodType periodType,
            String periodKey,
            LocalDateTime periodFrom,
            LocalDateTime periodTo) {
        this.apartmentComplex = apartmentComplex;
        this.periodType = periodType;
        this.periodKey = periodKey;
        this.periodFrom = periodFrom;
        this.periodTo = periodTo;
    }

    public void startGeneration() {
        this.generationStatus = AnalyticsInsightGenerationStatus.PROCESSING;
    }

    public void completeGeneration(String insightContent) {
        this.generationStatus = AnalyticsInsightGenerationStatus.COMPLETED;
        this.insightContent = insightContent;
    }

    public void failGeneration() {
        this.generationStatus = AnalyticsInsightGenerationStatus.FAILED;
        this.insightContent = null;
    }
}
