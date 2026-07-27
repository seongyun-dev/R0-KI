package com.oneloop.mapping.event;

import com.oneloop.mapping.domain.MappingStatus;

/** 지도 생성 세션의 상태가 실제로 변경된 경우 발행되는 내부 이벤트이다. */
public record MappingStatusChangedEvent(Long mappingSessionId, MappingStatus status) {}
