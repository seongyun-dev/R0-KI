package com.oneloop.analytics.event;

/**
 * AI 인사이트 비동기 생성 요청 이벤트.
 *
 * <p>조회 트랜잭션이 커밋된 뒤에만 Worker가 돌도록
 * {@code @TransactionalEventListener(AFTER_COMMIT)}와 함께 쓴다.
 */
public record AnalyticsInsightRequestedEvent(Long insightId) {}
