package com.oneloop.map.domain;

public enum CheckpointType {
    START("출발지"),
    PARKING("주차장"),
    RECYCLING_AREA("분리수거장"),
    DANGER_ZONE("위험 구역"),
    DESTINATION("도착지");

    private final String displayName;

    CheckpointType(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
