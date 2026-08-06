package com.oneloop.mapping.event;

import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.domain.MappingStopCommandStatus;

public record MappingStopCommandStatusChangedEvent(
        Long mappingSessionId,
        MappingStatus mappingStatus,
        String stopCommandId,
        MappingStopCommandStatus stopCommandStatus,
        String reason) {}
