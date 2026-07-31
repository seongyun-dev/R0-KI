package com.oneloop.global.exception;

import org.springframework.http.HttpStatus;

public enum ErrorCode {
    INVALID_ZONE_BOUNDS(
            HttpStatus.BAD_REQUEST, "ZONE_001", "구역은 너비와 높이가 있는 사각형이어야 합니다."),
    MAPPING_SESSION_ALREADY_EXISTS(
            HttpStatus.CONFLICT, "MAPPING_004", "아파트 단지 또는 로봇에 이미 지도 생성 세션이 존재합니다."),
    DUPLICATE_USERNAME(HttpStatus.CONFLICT, "AUTH_005", "이미 사용 중인 아이디입니다."),
    INVALID_INPUT(HttpStatus.BAD_REQUEST, "COMMON_001", "입력값이 올바르지 않습니다."),
    INVALID_JSON(HttpStatus.BAD_REQUEST, "COMMON_002", "요청 본문의 형식이 올바르지 않습니다."),
    UNAUTHORIZED(HttpStatus.UNAUTHORIZED, "AUTH_001", "인증이 필요합니다."),
    ACCESS_DENIED(HttpStatus.FORBIDDEN, "AUTH_002", "요청을 수행할 권한이 없습니다."),
    INVALID_CREDENTIALS(HttpStatus.UNAUTHORIZED, "AUTH_003", "아이디 또는 비밀번호가 올바르지 않습니다."),
    MEMBER_NOT_ACTIVE(HttpStatus.FORBIDDEN, "AUTH_004", "사용할 수 없는 계정입니다."),
    RESOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "COMMON_003", "요청한 리소스를 찾을 수 없습니다."),
    INTERNAL_SERVER_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "COMMON_999", "서버 내부 오류가 발생했습니다."),
    ROBOT_NOT_FOUND(HttpStatus.NOT_FOUND, "ROBOT_001", "존재하지 않는 순찰로봇입니다."),
    ROBOT_SERIAL_NUMBER_DUPLICATE(HttpStatus.CONFLICT, "ROBOT_002", "이미 등록된 시리얼 번호입니다."),
    MAPPING_SESSION_ALREADY_ACTIVE(
            HttpStatus.CONFLICT, "MAPPING_001", "해당 로봇에서 이미 지도 생성이 진행 중입니다."),
    MAPPING_SESSION_NOT_FOUND(
            HttpStatus.NOT_FOUND, "MAPPING_002", "지도 생성 세션을 찾을 수 없습니다."),
    MAPPING_SESSION_INVALID_STATE(HttpStatus.CONFLICT, "MAPPING_003", "현재 상태에서는 지도를 등록할 수 없습니다."),
    INVALID_MAP_FILE(HttpStatus.BAD_REQUEST, "MAP_001", "지도 이미지 파일이 올바르지 않습니다."),
    MAP_STORAGE_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "MAP_002", "지도 파일 저장에 실패했습니다."),
    MAP_NOT_FOUND(HttpStatus.NOT_FOUND, "MAP_003", "지도를 찾을 수 없습니다."),
    PATROL_NOT_FOUND(HttpStatus.NOT_FOUND, "PATROL_001", "존재하지 않는 순찰 기록입니다."),
    PATROL_ALREADY_IN_PROGRESS(HttpStatus.CONFLICT, "PATROL_002", "해당 로봇은 이미 순찰 중입니다."),
    EVENT_NOT_FOUND(HttpStatus.NOT_FOUND, "EVENT_001", "존재하지 않는 이벤트입니다."),
    FILE_STORAGE_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "EVENT_003", "파일 저장 중 오류가 발생했습니다."),
    NOTIFICATION_NOT_FOUND(HttpStatus.NOT_FOUND, "NOTI_001", "존재하지 않는 알림입니다.");

    private final HttpStatus status;
    private final String code;
    private final String message;

    ErrorCode(HttpStatus status, String code, String message) {
        this.status = status;
        this.code = code;
        this.message = message;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }
}
