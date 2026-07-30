package com.oneloop.global.gms.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "gms")
public class GmsProperties {

    private String baseUrl;
    private String apiKey;
    private String model;
    private String chatCompletionsPath = "/chat/completions";
    private int timeoutSeconds = 30;

    /**
     * 순찰 요약 응답 상한(추론+본문 합산).
     * gpt-5-nano 는 좀 멍청한 것 같다 그래서그런가 content 가 빈다. null이면 미전송.
     */
    private Integer summaryMaxCompletionTokens = 4096;

    /**
     * 통계 인사이트 응답 상한(추론+본문 합산).
     * 마크다운 5섹션 + 내부 추론 여유. null이면 미전송.
     */
    private Integer insightMaxCompletionTokens = 16384;
}
