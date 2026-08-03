package com.oneloop.robot.controller;

import com.oneloop.robot.service.RobotStreamSessionService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/internal/stream-sessions")
public class RobotStreamSessionInternalController {

    private final RobotStreamSessionService robotStreamSessionService;

    @GetMapping("/validate")
    public ResponseEntity<Void> validate(
            @RequestHeader("X-Stream-Robot-Id") Long robotId,
            @RequestHeader(value = "X-Stream-Token", required = false) String token) {
        if (robotStreamSessionService.validateAndConsume(robotId, token)) {
            return ResponseEntity.noContent().build();
        }
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
    }
}
