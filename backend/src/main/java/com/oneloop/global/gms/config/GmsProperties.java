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
}
