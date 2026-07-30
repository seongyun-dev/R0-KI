package com.oneloop.mqtt.dto;

import java.time.OffsetDateTime;

// hanbakwi/v1/robots/{robotKey}/command/ack 공용 응답 (PING/START_MAPPING/START_PATROL/STOP_PATROL 공통)
public record CommandAck(
        int schemaVersion,
        String commandId,
        String command,
        AckStatus status,
        OffsetDateTime receivedAt) {

    public enum AckStatus {
        SUCCEEDED,
        REJECTED,
        FAILED
    }
}
