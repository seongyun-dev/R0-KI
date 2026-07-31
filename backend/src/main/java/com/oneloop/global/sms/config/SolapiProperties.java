package com.oneloop.global.sms.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

// solapi(SMS 발송) API 키/시크릿/발신번호 설정값.
@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "solapi")
public class SolapiProperties {

    private String apiKey;
    private String apiSecret;
    private String senderNumber;
}
