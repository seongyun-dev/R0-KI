package com.oneloop.global.response;

import java.time.LocalDateTime;
import java.util.List;

public record ErrorResponse(LocalDateTime timestamp, List<ValidationError> validationErrors) {

    public static ErrorResponse now() {
        return new ErrorResponse(LocalDateTime.now(), List.of());
    }

    public static ErrorResponse withValidationErrors(List<ValidationError> validationErrors) {
        return new ErrorResponse(LocalDateTime.now(), validationErrors);
    }

    public record ValidationError(String field, String message) {}
}
