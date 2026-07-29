package com.oneloop.global.exception;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.response.ErrorResponse;
import com.oneloop.global.response.ErrorResponse.ValidationError;
import java.util.List;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiResponse<ErrorResponse>> handleBusinessException(
            BusinessException exception) {
        ErrorCode errorCode = exception.getErrorCode();
        return buildResponse(errorCode, exception.getMessage(), ErrorResponse.now());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponse<ErrorResponse>> handleValidationException(
            MethodArgumentNotValidException exception) {
        List<ValidationError> validationErrors =
                exception.getBindingResult().getFieldErrors().stream()
                        .map(this::toValidationError)
                        .toList();

        return buildResponse(
                ErrorCode.INVALID_INPUT,
                ErrorCode.INVALID_INPUT.getMessage(),
                ErrorResponse.withValidationErrors(validationErrors));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiResponse<ErrorResponse>> handleInvalidJson(
            HttpMessageNotReadableException exception) {
        log.warn("요청 본문 파싱 실패: {}", exception.getMessage());
        return buildResponse(
                ErrorCode.INVALID_JSON, ErrorCode.INVALID_JSON.getMessage(), ErrorResponse.now());
    }

    /** 필수 쿼리 파라미터 누락 (예: trend API의 bucket) */
    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ApiResponse<ErrorResponse>> handleMissingParameter(
            MissingServletRequestParameterException exception) {
        log.warn("필수 요청 파라미터 누락: {}", exception.getParameterName());
        return buildResponse(
                ErrorCode.INVALID_INPUT,
                ErrorCode.INVALID_INPUT.getMessage(),
                ErrorResponse.now());
    }

    /** enum 등 타입 변환 실패 (예: bucket=YEAR) */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiResponse<ErrorResponse>> handleArgumentTypeMismatch(
            MethodArgumentTypeMismatchException exception) {
        log.warn(
                "요청 파라미터 타입 불일치: name={}, value={}",
                exception.getName(),
                exception.getValue());
        return buildResponse(
                ErrorCode.INVALID_INPUT,
                ErrorCode.INVALID_INPUT.getMessage(),
                ErrorResponse.now());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<ErrorResponse>> handleUnexpectedException(
            Exception exception) {
        log.error("처리되지 않은 예외가 발생했습니다.", exception);
        return buildResponse(
                ErrorCode.INTERNAL_SERVER_ERROR,
                ErrorCode.INTERNAL_SERVER_ERROR.getMessage(),
                ErrorResponse.now());
    }

    private ValidationError toValidationError(FieldError fieldError) {
        return new ValidationError(fieldError.getField(), fieldError.getDefaultMessage());
    }

    private ResponseEntity<ApiResponse<ErrorResponse>> buildResponse(
            ErrorCode errorCode, String message, ErrorResponse errorResponse) {
        return ResponseEntity.status(errorCode.getStatus())
                .body(ApiResponse.error(errorCode.getCode(), message, errorResponse));
    }
}
