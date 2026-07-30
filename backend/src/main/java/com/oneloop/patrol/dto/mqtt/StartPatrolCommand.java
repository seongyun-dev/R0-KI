package com.oneloop.patrol.dto.mqtt;

import java.time.OffsetDateTime;
import java.time.ZoneId;

// hanbakwi/v1/robots/{robotKey}/command로 발행하는 순찰 시작 명령
public record StartPatrolCommand(
        int schemaVersion,
        String commandId,
        String command,
        Long patrolId,
        OffsetDateTime issuedAt,
        OffsetDateTime expiresAt) {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final long COMMAND_VALIDITY_SECONDS = 10;

    public static StartPatrolCommand of(String commandId, Long patrolId) {
        OffsetDateTime issuedAt = OffsetDateTime.now(SERVICE_ZONE);
        return new StartPatrolCommand(
                1,
                commandId,
                "START_PATROL",
                patrolId,
                issuedAt,
                issuedAt.plusSeconds(COMMAND_VALIDITY_SECONDS));
    }
}
