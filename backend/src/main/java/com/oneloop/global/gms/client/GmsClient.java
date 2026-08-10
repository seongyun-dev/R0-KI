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

    /**
     * 순찰 1건 요약용 시스템 프롬프트.
     *
     * <p>왜 분리했나: 순찰 요약은 "이번 순찰에서 무슨 일이 있었는지"가 목적이다.
     * 통계 인사이트(주/월 운영 방향)와 역할이 달라, 같은 프롬프트를 쓰면
     * 모델이 순찰 일지 톤으로 답하거나 집계 숫자를 무시하기 쉽다.
     */
    private static final String PATROL_SUMMARY_SYSTEM_PROMPT =
            """
            당신은 아파트 순찰 기록을 관리자가 확인하기 쉽게 요약하는 도우미입니다.
            제공된 데이터에 없는 사실을 만들지 마세요.
            이벤트의 위치는 체크포인트 이름을 우선 사용하세요.
            긴급 이벤트와 미처리 이벤트를 우선적으로 언급하세요.
            이벤트가 없으면 특이사항이 없다고 작성하세요.
            개인정보와 차량번호를 노출하지 마세요.
            한국어 3~5문장의 일반 텍스트만 반환하세요.
            """;

    /**
     * 통계 AI 인사이트용 시스템 프롬프트.
     *
     * <p>입력은 백엔드가 만든 마크다운 표이다.
     * 표 숫자를 그대로 나열하지 말고, 경비원이 바로 움직일 문장으로 다시 쓰게 한다.
     */
    private static final String ANALYTICS_INSIGHT_SYSTEM_PROMPT =
            """
            당신은 아파트 경비원에게 지난 주/월 순찰 이상상황을 알려주는 도우미입니다.
            입력은 백엔드가 이미 계산해 둔 마크다운 표입니다. 표에 없는 숫자·구역·원인을 만들지 마세요.

            [반드시 지킬 것]
            1. 표에 있는 값만 사용하세요. 추측 금지.
            2. 표가 비어 있거나 전부 0이면 ## 안내 아래 "지난 기간에 특별히 확인할 일은 없었습니다."만 쓰세요.
            3. 개인정보와 차량번호를 쓰지 마세요.
            4. 영문 코드를 쓰지 마세요. 표의 한글 명칭을 그대로 쓰세요.
            5. 인력 재배치·예산·정책 제안은 하지 마세요.
            6. 반드시 마크다운으로 작성하세요. 각 섹션은 ## 제목, 항목은 - 불릿입니다.
            7. 표의 모든 숫자를 한 줄에 나열하지 마세요. 중요한 변화·미처리·우선 구역만 골라 쉬운 문장으로 쓰세요.
            8. 5개 섹션을 모두 끝까지 작성하세요. 문장은 반드시 마침표로 끝내고, 중간에 끊지 마세요.
            9. 서론/결론("다음은 ~입니다")과 코드블록은 쓰지 마세요.

            [출력 형식 — 아래 다섯 제목을 빠짐없이 쓰고, 각 항목은 짧은 문장으로]
            ## 종합 요약
            - 이번 기간 이상상황·순찰·미처리가 어땠는지 한두 문장으로 적어 주세요.
            - 지난 기간과 비교해 눈에 띄는 변화가 있으면 한 문장 더 적어 주세요. 지난 기간 수치가 0이면 이 줄은 생략하세요.

            ## 유형별 현황
            - 가장 많이 나온 유형과 건수를 적어 주세요.
            - 미처리가 남은 유형이 있으면 어떤 유형인지 적어 주세요.

            ## 중점 확인 구역
            - 가장 먼저 확인할 구역과 그 이유를 적어 주세요.
            - 추가로 확인할 구역이 있으면 이어서 적어 주세요.

            ## 처리 현황
            - 처리완료와 미처리가 각각 어느지 짧게 정리해 주세요.

            ## 우선 조치 사항
            - 우선 확인할 미처리 한 가지를 짧게 적어 주세요.
            - 필요하면 다음 조치 사항을 한 문장 더 적어 주세요.
            """;

    private final RestClient gmsRestClient;
    private final GmsProperties properties;

    /** 순찰 1건 AI 요약. 기존 PatrolAiSummaryWorker가 사용한다. */
    public String summarize(String patrolDataJson) {
        return chat(
                PATROL_SUMMARY_SYSTEM_PROMPT,
                "다음 순찰 기록을 요약하세요.\n\n" + patrolDataJson,
                properties.getSummaryMaxCompletionTokens());
    }

    /**
     * 통계(주/월) AI 인사이트 생성.
     *
     * <p>입력은 {@code AnalyticsInsightTableBuilder}가 만든 마크다운 표이다.
     */
    public String generateAnalyticsInsight(String tablesMarkdown) {
        return chat(
                ANALYTICS_INSIGHT_SYSTEM_PROMPT,
                "아래 표만 보고 아파트 경비원이 웹에서 바로 읽을 마크다운 현장 안내를 작성하세요.\n"
                        + "5개 섹션을 모두 완성하고, 마지막 문장까지 마침표로 끝내세요.\n"
                        + "표 숫자를 그대로 복사하지 말고 쉬운 문장으로 다시 쓰세요.\n\n"
                        + tablesMarkdown,
                properties.getInsightMaxCompletionTokens());
    }

    /**
     * GMS Chat Completions 공통 호출.
     *
     * <p>role=developer 는 기존 순찰 요약과 동일한 GMS 프로토콜이다.
     * max_completion_tokens 는 추론+본문 합산 예산이다(gpt-5-nano).
     * 값이 너무 낮으면 finish_reason=length 로 content 가 빈다.
     */
    private String chat(String systemPrompt, String userContent, Integer maxCompletionTokens) {
        validateConfiguration();

        GmsChatRequest request =
                GmsChatRequest.builder()
                        .model(properties.getModel())
                        .maxCompletionTokens(maxCompletionTokens)
                        .messages(
                                List.of(
                                        GmsChatRequest.Message.builder()
                                                .role("developer")
                                                .content(systemPrompt)
                                                .build(),
                                        GmsChatRequest.Message.builder()
                                                .role("user")
                                                .content(userContent)
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
            String finishReason =
                    response != null
                                    && response.getChoices() != null
                                    && !response.getChoices().isEmpty()
                            ? response.getChoices().getFirst().getFinishReason()
                            : null;
            throw new IllegalStateException(
                    "GMS가 유효한 요약 내용을 반환하지 않았습니다. finishReason="
                            + finishReason
                            + ", maxCompletionTokens="
                            + maxCompletionTokens);
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
