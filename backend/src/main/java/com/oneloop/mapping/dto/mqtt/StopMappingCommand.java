package com.oneloop.mapping.dto.mqtt;

import java.time.OffsetDateTime;
import java.time.ZoneId;

public record StopMappingCommand(
        int schemaVersion,
        Long mappingSessionId,
        String commandId,
        String command,
        OffsetDateTime issuedAt,
        OffsetDateTime expiresAt) {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final long COMMAND_VALIDITY_SECONDS = 10;

    public static StopMappingCommand of(String commandId, Long mappingSessionId) {
        OffsetDateTime issuedAt = OffsetDateTime.now(SERVICE_ZONE);
        return new StopMappingCommand(
                1,
                mappingSessionId,
                commandId,
                "STOP_MAPPING",
                issuedAt,
                issuedAt.plusSeconds(COMMAND_VALIDITY_SECONDS));
    }
}
