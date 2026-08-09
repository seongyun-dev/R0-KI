package com.oneloop.robot.dto.mqtt;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

// hanbakwi/v1/robots/{robotKey}/pose payload.
public record RobotPoseMessage(
        int schemaVersion,
        String robotKey,
        BigDecimal x,
        BigDecimal y,
        BigDecimal heading,
        OffsetDateTime timestamp) {}
