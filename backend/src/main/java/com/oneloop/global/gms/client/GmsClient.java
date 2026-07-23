package com.oneloop.global.gms.client;

import com.oneloop.global.gms.config.GmsProperties;
import com.oneloop.global.gms.dto.GmsChatRequest;
import com.oneloop.global.gms.dto.GmsChatResponse;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

@Component
@RequiredArgsConstructor
public class GmsClient {

    private static final String SYSTEM_PROMPT =
            """
            당신은 아파트 순찰 기록을 관리자가 확인하기 쉽게 요약하는 도우미입니다.
            제공된 데이터에 없는 사실을 만들지 마세요.
            이벤트의 위치는 체크포인트 이름을 우선 사용하세요.
            긴급 이벤트와 미처리 이벤트를 우선적으로 언급하세요.
            이벤트가 없으면 특이사항이 없다고 작성하세요.
            개인정보와 차량번호를 노출하지 마세요.
            한국어 3~5문장의 일반 텍스트만 반환하세요.
            """;

    private final RestClient gmsRestClient;
    private final GmsProperties properties;

    public String summarize(String patrolDataJson) {
        validateConfiguration();

        GmsChatRequest request =
                GmsChatRequest.builder()
                        .model(properties.getModel())
                        .messages(
                                List.of(
                                        GmsChatRequest.Message.builder()
                                                .role("developer")
                                                .content(SYSTEM_PROMPT)
                                                .build(),
                                        GmsChatRequest.Message.builder()
                                                .role("user")
                                                .content("다음 순찰 기록을 요약하세요.\n\n" + patrolDataJson)
                                                .build()))
                        .build();

        GmsChatResponse response =
                gmsRestClient
                        .post()
                        .uri(properties.getChatCompletionsPath())
                        .body(request)
                        .retrieve()
                        .body(GmsChatResponse.class);

        if (response == null
                || response.getChoices() == null
                || response.getChoices().isEmpty()
                || response.getChoices().getFirst().getMessage() == null
                || !StringUtils.hasText(
                        response.getChoices().getFirst().getMessage().getContent())) {
            throw new IllegalStateException("GMS가 유효한 요약 내용을 반환하지 않았습니다.");
        }
        return response.getChoices().getFirst().getMessage().getContent().trim();
    }

    private void validateConfiguration() {
        if (!StringUtils.hasText(properties.getApiKey())
                || !StringUtils.hasText(properties.getModel())) {
            throw new IllegalStateException("GMS_KEY와 GMS_MODEL 설정이 필요합니다.");
        }
    }
}
