package com.oneloop.analytics.dto.request;

import com.oneloop.event.domain.EventType;
import java.util.EnumSet;
import java.util.Set;

/**
 * 프론트 통계 화면용 이벤트 유형 묶음.
 *
 * <p>백엔드 EventType(5종)을 화면 라벨(주차/쓰레기)로 묶는 기준이다.
 * handling API와 (필요 시) 프론트 매퍼가 이 규칙을 공유한다.
 *
 * <ul>
 *   <li>주차: 불법주차 + 미등록차량
 *   <li>쓰레기: 쓰레기 투기 + 분리수거 포화
 * </ul>
 */
public enum AnalyticsEventGroup {
    PARKING("주차", EnumSet.of(EventType.ILLEGAL_PARKING, EventType.UNREGISTERED_VEHICLE)),
    TRASH("쓰레기", EnumSet.of(EventType.TRASH_DETECTED, EventType.RECYCLING_AREA_FULL));

    private final String label;
    private final Set<EventType> eventTypes;

    AnalyticsEventGroup(String label, Set<EventType> eventTypes) {
        this.label = label;
        this.eventTypes = eventTypes;
    }

    public String getLabel() {
        return label;
    }

    public Set<EventType> getEventTypes() {
        return eventTypes;
    }

    /** 해당 EventType이 이 그룹에 속하는지 */
    public boolean contains(EventType type) {
        return eventTypes.contains(type);
    }
}
