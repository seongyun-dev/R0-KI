package com.oneloop.robot.event;

import com.oneloop.robot.domain.ObstacleStatus;

// 로봇이 장애물에 막히거나(STOP) 해제될 때(CLEAR) 발행
public record RobotObstacleEvent(Long robotId, ObstacleStatus status, String direction, String message) {}
