package com.oneloop.analytics.dto.request;

/**
 * 추이 집계 단위.
 * 프론트가 차트 X축을 일/주/월 중 어떤 간격으로 그릴지 정할 때 사용한다.
 */
public enum AnalyticsBucket {
    day,
    week,
    month
}
