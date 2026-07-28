package com.oneloop.global.file;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

// 로컬 디스크에 파일을 저장하는 FileStorageService 구현체
@Service
@RequiredArgsConstructor
public class LocalFileStorageService implements FileStorageService {

    private final FileStorageProperties properties;

    // 파일을 uploadDir에 UUID 파일명으로 저장하고, 접근용 URL(urlPrefix + 파일명)을 반환
    @Override
    public String store(MultipartFile file) {
        String filename = UUID.randomUUID() + resolveExtension(file.getOriginalFilename());
        try {
            Path uploadDir = Path.of(properties.getUploadDir());
            Files.createDirectories(uploadDir);
            file.transferTo(uploadDir.resolve(filename));
        } catch (IOException e) {
            throw new BusinessException(ErrorCode.FILE_STORAGE_FAILED);
        }
        return properties.getUrlPrefix() + "/" + filename;
    }

    // 원본 파일명에서 확장자(".jpg" 등)만 추출. 확장자가 없으면 빈 문자열
    private String resolveExtension(String originalFilename) {
        if (!StringUtils.hasText(originalFilename) || !originalFilename.contains(".")) {
            return "";
        }
        return originalFilename.substring(originalFilename.lastIndexOf('.'));
    }
}
