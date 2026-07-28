package com.oneloop.global.file;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

// 로컬 파일 저장 경로와, 저장된 파일에 접근할 URL 접두사 설정
@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "app.file-storage")
public class FileStorageProperties {

    private String uploadDir = "uploads";
    private String urlPrefix = "/uploads";
    private String mapSubdirectory = "maps";
}
