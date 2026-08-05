package com.oneloop.map.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.request.MapUploadRequest;
import com.oneloop.map.dto.response.MapDetailResponse;
import com.oneloop.map.dto.response.MapUploadResponse;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.service.MapFileStorage.StoredMapFile;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.event.MappingStatusChangedEvent;
import com.oneloop.mapping.repository.MappingSessionRepository;
import java.util.Objects;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MapService {

    private static final String MAP_FILE_URL_PREFIX = "/api/map/files/";

    private final MappingSessionRepository mappingSessionRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final MapFileStorage mapFileStorage;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public MapUploadResponse upload(
            Long mappingSessionId, Long authenticatedRobotId, MapUploadRequest request) {
        // 세션 ID와 commandId를 함께 잠금 조회하여 재시도나 동시 업로드의 중복 반영을 막는다.
        MappingSession session =
                mappingSessionRepository
                        .findForUpdateByIdAndCommandId(mappingSessionId, request.getCommandId())
                        .orElseThrow(
                                () -> new BusinessException(ErrorCode.MAPPING_SESSION_NOT_FOUND));

        if (!Objects.equals(session.getRobot().getId(), authenticatedRobotId)) {
            throw new BusinessException(ErrorCode.ACCESS_DENIED);
        }

        // 네트워크 문제로 완료 응답을 받지 못한 로봇의 동일 요청은 기존 결과를 반환한다.
        if (session.getStatus() == MappingStatus.COMPLETED) {
            PatrolMap completedMap =
                    patrolMapRepository
                            .findByApartmentComplexId(session.getApartmentComplex().getId())
                            .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));
            return MapUploadResponse.from(session, completedMap);
        }

        if (session.getStatus() != MappingStatus.MAPPING) {
            throw new BusinessException(ErrorCode.MAPPING_SESSION_INVALID_STATE);
        }

        StoredMapFile storedFile = mapFileStorage.store(request.getMapImage());
        PatrolMap patrolMap =
                patrolMapRepository
                        .findByApartmentComplexId(session.getApartmentComplex().getId())
                        .orElse(null);
        String previousMapUrl = patrolMap == null ? null : patrolMap.getUrl();

        registerFileCleanup(storedFile.publicUrl(), previousMapUrl);

        if (patrolMap == null) {
            patrolMap =
                    patrolMapRepository.save(
                            new PatrolMap(
                                    session.getApartmentComplex(),
                                    createMapName(session),
                                    storedFile.publicUrl(),
                                    request.getResolution(),
                                    request.getOriginX(),
                                    request.getOriginY(),
                                    request.getOriginYaw(),
                                    storedFile.width(),
                                    storedFile.height()));
        } else {
            patrolMap.update(
                    createMapName(session),
                    storedFile.publicUrl(),
                    request.getResolution(),
                    request.getOriginX(),
                    request.getOriginY(),
                    request.getOriginYaw(),
                    storedFile.width(),
                    storedFile.height());
        }

        session.complete();
        eventPublisher.publishEvent(
                new MappingStatusChangedEvent(
                        session.getId(), MappingStatus.COMPLETED, patrolMap.getId()));

        return MapUploadResponse.from(session, patrolMap);
    }

    public MapDetailResponse get(Long apartmentComplexId, Long mapId) {
        PatrolMap patrolMap =
                patrolMapRepository
                        .findByIdAndApartmentComplexId(mapId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));
        return MapDetailResponse.from(patrolMap);
    }

    public MapDetailResponse getCurrent(Long apartmentComplexId) {
        PatrolMap patrolMap =
                patrolMapRepository
                        .findByApartmentComplexId(apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));
        return MapDetailResponse.from(patrolMap);
    }

    public Resource getFile(Long apartmentComplexId, String storedName) {
        String mapUrl = MAP_FILE_URL_PREFIX + storedName;
        patrolMapRepository
                .findByUrlAndApartmentComplexId(mapUrl, apartmentComplexId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));
        return mapFileStorage.load(storedName);
    }

    private String createMapName(MappingSession session) {
        return session.getApartmentComplex().getName() + " 순찰 지도";
    }

    private void registerFileCleanup(String newMapUrl, String previousMapUrl) {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        if (previousMapUrl != null && !previousMapUrl.equals(newMapUrl)) {
                            mapFileStorage.deleteByUrl(previousMapUrl);
                        }
                    }

                    @Override
                    public void afterCompletion(int status) {
                        if (status != STATUS_COMMITTED) {
                            mapFileStorage.deleteByUrl(newMapUrl);
                        }
                    }
                });
    }
}
