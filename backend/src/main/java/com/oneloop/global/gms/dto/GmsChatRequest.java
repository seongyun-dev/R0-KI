package com.oneloop.global.gms.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
public class GmsChatRequest {

    private String model;
    private List<Message> messages;

    /**
     * 응답 최대 토큰.
     * 최신 OpenAI 호환 API는 max_completion_tokens 를 쓴다.
     */
    @JsonProperty("max_completion_tokens")
    private Integer maxCompletionTokens;

    @Getter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class Message {
        private String role;
        private String content;
    }
}
