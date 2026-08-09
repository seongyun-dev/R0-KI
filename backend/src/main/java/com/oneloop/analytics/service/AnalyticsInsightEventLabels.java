package com.oneloop.analytics.service;

import com.oneloop.event.domain.EventType;

/**
 * LLM 인사이트용 이벤트 유형 한글 라벨.
 *
 * <p>화면 API 응답의 enum 원문을 LLM에 그대로 주지 않기 위해,
 * 표 빌더에서만 이 매핑을 사용한다.
 */
public final class AnalyticsInsightEventLabels {

    private AnalyticsInsightEventLabels() {}

    public static String toKorean(EventType type) {
        if (type == null) {
            return "기타";
        }
        return switch (type) {
            case ILLEGAL_PARKING -> "불법주차";
            case UNREGISTERED_VEHICLE -> "미등록 차량";
            case TRASH_DETECTED -> "쓰레기";
            case RECYCLING_AREA_FULL -> "분리수거장 포화";
            case EMERGENCY -> "응급상황";
        };
    }
}
