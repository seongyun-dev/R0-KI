package com.oneloop.patrol.dto.mqtt;

import java.time.OffsetDateTime;
import java.time.ZoneId;

/** Explicit operator-authorized resume for a patrol held by an AI emergency. */
public record ResumePatrolCommand(
        int schemaVersion,
        String commandId,
        String command,
        Long patrolId,
        OffsetDateTime issuedAt,
        OffsetDateTime expiresAt) {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final long COMMAND_VALIDITY_SECONDS = 10;

    public static ResumePatrolCommand of(String commandId, Long patrolId) {
        OffsetDateTime issuedAt = OffsetDateTime.now(SERVICE_ZONE);
        return new ResumePatrolCommand(
                1,
                commandId,
                "RESUME_PATROL",
                patrolId,
                issuedAt,
                issuedAt.plusSeconds(COMMAND_VALIDITY_SECONDS));
    }
}
