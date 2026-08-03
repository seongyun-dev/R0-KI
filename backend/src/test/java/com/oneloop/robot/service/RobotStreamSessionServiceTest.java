package com.oneloop.robot.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class RobotStreamSessionServiceTest {

    private static final Instant NOW = Instant.parse("2026-08-03T00:00:00Z");

    @Test
    void issuedTokenIsValidOnlyOnceForTheSameRobot() {
        RobotStreamSessionService service =
                new RobotStreamSessionService(
                        Duration.ofSeconds(60), Clock.fixed(NOW, ZoneOffset.UTC));
        String token = service.issue(16L).token();

        assertThat(service.validateAndConsume(17L, token)).isFalse();
        assertThat(service.validateAndConsume(16L, token)).isFalse();

        token = service.issue(16L).token();
        assertThat(service.validateAndConsume(16L, token)).isTrue();
        assertThat(service.validateAndConsume(16L, token)).isFalse();
    }

    @Test
    void expiredTokenIsRejected() {
        RobotStreamSessionService issuer =
                new RobotStreamSessionService(
                        Duration.ZERO, Clock.fixed(NOW, ZoneOffset.UTC));

        assertThat(issuer.validateAndConsume(16L, issuer.issue(16L).token())).isFalse();
    }
}
