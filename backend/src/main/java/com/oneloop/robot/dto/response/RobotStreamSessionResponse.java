package com.oneloop.robot.dto.response;

import java.time.Instant;

public record RobotStreamSessionResponse(String token, Instant expiresAt) {}
