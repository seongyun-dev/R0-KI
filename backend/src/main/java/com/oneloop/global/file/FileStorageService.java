package com.oneloop.global.file;

import org.springframework.web.multipart.MultipartFile;

// 파일을 저장하고, 저장된 파일에 접근 가능한 URL을 반환하는 인터페이스. 로컬/S3 등 구현체를 교체할 수 있도록 분리
public interface FileStorageService {
    String store(MultipartFile file);
}
