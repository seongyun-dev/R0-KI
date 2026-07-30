package com.oneloop.analytics.dto.internal;

import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

/**
 * LLM에 넣을 인사이트 입력.
 *
 * <p>통짜 overview/trend DTO JSON 대신, 표 빌더가 만든 마크다운 표 문자열만 담는다.
 */
@Getter
@Builder
public class AnalyticsInsightSnapshot {

    private String periodType;
    private String periodKey;
    private LocalDateTime periodFrom;
    private LocalDateTime periodTo;
    private String timezone;

    /** 메타 + 4개 표가 포함된 마크다운 본문 */
    private String tablesMarkdown;
}
