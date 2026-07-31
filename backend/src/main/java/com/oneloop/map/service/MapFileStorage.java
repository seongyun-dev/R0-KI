package com.oneloop.map.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.file.FileStorageProperties;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import javax.imageio.ImageIO;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

@Component
public class MapFileStorage {

    private static final long MAX_MAP_FILE_SIZE = 20L * 1024 * 1024;
    private static final String PNG_CONTENT_TYPE = "image/png";
    private static final String PUBLIC_URL_PREFIX = "/api/map/files/";

    private final Path storageDirectory;

    public MapFileStorage(FileStorageProperties properties) {
        storageDirectory =
                Path.of(properties.getMapDir()).toAbsolutePath().normalize();
    }

    public StoredMapFile store(MultipartFile file) {
        validate(file);

        try {
            Files.createDirectories(storageDirectory);
            String storedName = UUID.randomUUID() + ".png";
            Path target = resolve(storedName);
            Path temporary = Files.createTempFile(storageDirectory, "upload-", ".tmp");

            try {
                file.transferTo(temporary);
                ImageDimensions dimensions = readPngDimensions(temporary);
                moveToFinalLocation(temporary, target);
                return new StoredMapFile(
                        storedName, PUBLIC_URL_PREFIX + storedName, dimensions.width(), dimensions.height());
            } finally {
                Files.deleteIfExists(temporary);
            }
        } catch (BusinessException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MAP_STORAGE_FAILED);
        }
    }

    public Resource load(String storedName) {
        try {
            Path file = resolve(storedName);
            Resource resource = new UrlResource(file.toUri());
            if (!resource.exists() || !resource.isReadable()) {
                throw new BusinessException(ErrorCode.MAP_NOT_FOUND);
            }
            return resource;
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new BusinessException(ErrorCode.MAP_NOT_FOUND);
        }
    }

    public void deleteByUrl(String mapUrl) {
        if (mapUrl == null || !mapUrl.startsWith(PUBLIC_URL_PREFIX)) {
            return;
        }

        String storedName = mapUrl.substring(PUBLIC_URL_PREFIX.length());
        try {
            Files.deleteIfExists(resolve(storedName));
        } catch (IOException ignored) {
            // DB 반영은 끝난 상태이므로 파일 정리 실패가 API 성공 여부를 바꾸지 않게 한다.
        }
    }

    private void validate(MultipartFile file) {
        if (file == null
                || file.isEmpty()
                || file.getSize() > MAX_MAP_FILE_SIZE
                || !PNG_CONTENT_TYPE.equalsIgnoreCase(file.getContentType())) {
            throw new BusinessException(ErrorCode.INVALID_MAP_FILE);
        }
    }

    private void moveToFinalLocation(Path temporary, Path target) throws IOException {
        try {
            Files.move(
                    temporary,
                    target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private ImageDimensions readPngDimensions(Path file) throws IOException {
        try (InputStream inputStream = Files.newInputStream(file)) {
            BufferedImage image = ImageIO.read(inputStream);
            if (image == null) {
                throw new BusinessException(ErrorCode.INVALID_MAP_FILE);
            }
            return new ImageDimensions(image.getWidth(), image.getHeight());
        }
    }

    private Path resolve(String storedName) {
        Path resolved = storageDirectory.resolve(storedName).normalize();
        if (!resolved.getParent().equals(storageDirectory)) {
            throw new BusinessException(ErrorCode.MAP_NOT_FOUND);
        }
        return resolved;
    }

    private record ImageDimensions(int width, int height) {}

    public record StoredMapFile(String storedName, String publicUrl, int width, int height) {}
}
