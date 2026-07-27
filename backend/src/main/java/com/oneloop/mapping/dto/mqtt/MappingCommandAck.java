package com.oneloop.mapping.dto.mqtt;

import java.time.OffsetDateTime;

public record MappingCommandAck(
        int schemaVersion,
        String commandId,
        String command,
        Long mappingSessionId,
        AckResult result,
        OffsetDateTime receivedAt) {

    public enum AckResult {
        ACCEPTED,
        REJECTED
    }
}
