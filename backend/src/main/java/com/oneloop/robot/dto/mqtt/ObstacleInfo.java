package com.oneloop.robot.dto.mqtt;

import com.oneloop.robot.domain.ObstacleStatus;

// status 메시지에 실려오는 장애물 스냅샷. status=STOP이면 로봇이 막혀서 정지한 상태, CLEAR면 해제됨
public record ObstacleInfo(ObstacleStatus status, String direction, String reasonMessage) {}
