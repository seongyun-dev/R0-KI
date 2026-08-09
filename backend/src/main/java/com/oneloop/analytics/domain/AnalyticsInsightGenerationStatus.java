package com.oneloop.analytics.domain;

/**
 * AI 인사이트 LLM 생성 상태.
 *
 * <p>순찰 AI 요약({@code AiSummaryGenerationStatus})과 동일한 상태 머신이다.
 * analytics 도메인에 따로 두어 순찰 패키지에 의존하지 않는다.
 */
public enum AnalyticsInsightGenerationStatus {
    PENDING,
    PROCESSING,
    COMPLETED,
    FAILED
}
