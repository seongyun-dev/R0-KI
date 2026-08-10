package com.oneloop.patrol.dto.mqtt;

import java.time.OffsetDateTime;
import java.time.ZoneId;

// hanbakwi/v1/robots/{robotKey}/command로 발행하는 순찰 종료 명령. 백엔드가 pose로 도착을 확인한 뒤 자동 발행한다.
public record StopPatrolCommand(
        int schemaVersion,
        String commandId,
        String command,
        OffsetDateTime issuedAt,
        OffsetDateTime expiresAt) {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final long COMMAND_VALIDITY_SECONDS = 10;

    public static StopPatrolCommand of(String commandId) {
        OffsetDateTime issuedAt = OffsetDateTime.now(SERVICE_ZONE);
        return new StopPatrolCommand(
                1,
                commandId,
                "STOP_PATROL",
                issuedAt,
                issuedAt.plusSeconds(COMMAND_VALIDITY_SECONDS));
    }
}
