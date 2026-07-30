package com.oneloop.analytics.domain;

/**
 * AI 인사이트 집계 기간 유형.
 *
 * <p>화면의 week/month와 대응하며, 실제 분석 대상은 "직전 완료 구간"이다.
 * - WEEK: 지난주 (월~일)
 * - MONTH: 지난달
 */
public enum AnalyticsInsightPeriodType {
    WEEK,
    MONTH
}
