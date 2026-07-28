package com.oneloop.global.file;

import java.nio.file.Path;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

// LocalFileStorageService가 저장한 파일을 urlPrefix 경로로 그대로 내려받을 수 있게 정적 리소스로 매핑
@Configuration
@RequiredArgsConstructor
public class FileStorageWebConfig implements WebMvcConfigurer {

    private final FileStorageProperties properties;

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String location = "file:" + Path.of(properties.getUploadDir()).toAbsolutePath() + "/";
        // /uploads/로 시작하는 모든 요청을 처리
        registry.addResourceHandler(properties.getUrlPrefix() + "/**").addResourceLocations(location);
    }
}
