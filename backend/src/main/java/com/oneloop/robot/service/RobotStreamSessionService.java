package com.oneloop.robot.service;

import com.oneloop.robot.dto.response.RobotStreamSessionResponse;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class RobotStreamSessionService {

    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final Base64.Encoder TOKEN_ENCODER = Base64.getUrlEncoder().withoutPadding();

    private final Map<String, StreamSession> sessions = new ConcurrentHashMap<>();
    private final Duration lifetime;
    private final Clock clock;

    public RobotStreamSessionService(
            @Value("${app.stream.session-lifetime:60s}") Duration lifetime) {
        this(lifetime, Clock.systemUTC());
    }

    RobotStreamSessionService(Duration lifetime, Clock clock) {
        this.lifetime = lifetime;
        this.clock = clock;
    }

    public RobotStreamSessionResponse issue(Long robotId) {
        removeExpired();

        byte[] randomBytes = new byte[32];
        SECURE_RANDOM.nextBytes(randomBytes);
        String token = TOKEN_ENCODER.encodeToString(randomBytes);
        Instant expiresAt = clock.instant().plus(lifetime);
        sessions.put(token, new StreamSession(robotId, expiresAt));
        return new RobotStreamSessionResponse(token, expiresAt);
    }

    public boolean validateAndConsume(Long robotId, String token) {
        if (token == null || token.isBlank()) {
            return false;
        }

        StreamSession session = sessions.get(token);
        if (session == null
                || !session.robotId().equals(robotId)
                || !session.expiresAt().isAfter(clock.instant())) {
            sessions.remove(token);
            return false;
        }
        return sessions.remove(token, session);
    }

    private void removeExpired() {
        Instant now = clock.instant();
        sessions.entrySet().removeIf(entry -> !entry.getValue().expiresAt().isAfter(now));
    }

    private record StreamSession(Long robotId, Instant expiresAt) {}
}
