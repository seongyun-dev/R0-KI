package com.oneloop.global.sms.config;

import com.solapi.sdk.SolapiClient;
import com.solapi.sdk.message.service.DefaultMessageService;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// solapi SDK의 메시지 발송 클라이언트를 빈으로 등록한다.
@Configuration
@RequiredArgsConstructor
public class SolapiClientConfig {

    private final SolapiProperties properties;

    // API 키/시크릿으로 solapi 클라이언트를 한 번만 생성해 싱글턴 빈으로 등록한다
    @Bean
    public DefaultMessageService defaultMessageService() {
        return SolapiClient.INSTANCE.createInstance(properties.getApiKey(), properties.getApiSecret());
    }
}
