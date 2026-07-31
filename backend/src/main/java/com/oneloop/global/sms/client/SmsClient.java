package com.oneloop.global.sms.client;
import com.oneloop.global.sms.config.SolapiProperties;
import com.solapi.sdk.message.exception.SolapiMessageNotReceivedException;
import com.solapi.sdk.message.model.Message;
import com.solapi.sdk.message.service.DefaultMessageService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

// solapi로 SMS를 발송하는 클라이언트.
@Slf4j
@Component
@RequiredArgsConstructor
public class SmsClient {

    private final DefaultMessageService messageService;
    private final SolapiProperties properties;

    // 문자 한 건을 발송한다.
    public void send(String to, String text) {
        if (!StringUtils.hasText(properties.getSenderNumber())) {
            throw new IllegalStateException("SOLAPI_SENDER_NUMBER 설정이 필요합니다.");
        }

        Message message = new Message();
        message.setFrom(properties.getSenderNumber());
        message.setTo(to);
        message.setText(text);

        try {
            messageService.send(message);
        } catch (SolapiMessageNotReceivedException exception) {
            log.warn("SMS 발송 거부: {}", exception.getFailedMessageList());
            throw new IllegalStateException("SMS 발송에 실패했습니다.", exception);
        } catch (Exception exception) {
            throw new IllegalStateException("SMS 발송에 실패했습니다.", exception);
        }
    }
}
