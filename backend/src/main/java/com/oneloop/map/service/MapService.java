package com.oneloop.map.service;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.MapStatus;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.request.MapUploadRequest;
import com.oneloop.map.dto.response.MapDetailResponse;
import com.oneloop.map.dto.response.MapListResponse;
import com.oneloop.map.dto.response.MapUploadResponse;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.NavigationWaypointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.service.MapFileStorage.StoredMapFile;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.event.MappingStatusChangedEvent;
import com.oneloop.mapping.repository.MappingSessionRepository;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import com.oneloop.patrol.repository.PatrolRepository;
import java.util.Comparator;
import java.util.List;
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
    private final CheckpointRepository checkpointRepository;
    private final NavigationWaypointRepository navigationWaypointRepository;
    private final PatrolRepository patrolRepository;
    private final PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;
    private final NavigationConfigurationGuard navigationConfigurationGuard;
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
            PatrolMap completedMap = session.getResultMap();
            if (completedMap == null) {
                throw new BusinessException(ErrorCode.MAP_NOT_FOUND);
            }
            return MapUploadResponse.from(session, completedMap);
        }

        if (session.getStatus() != MappingStatus.MAPPING) {
            throw new BusinessException(ErrorCode.MAPPING_SESSION_INVALID_STATE);
        }

        ApartmentComplex apartmentComplex = session.getApartmentComplex();
        navigationConfigurationGuard.assertMutable(apartmentComplex.getId());

        StoredMapFile storedFile = mapFileStorage.store(request.getMapImage());
        registerRollbackFileCleanup(storedFile.publicUrl());

        PatrolMap previousActive =
                patrolMapRepository
                        .findForUpdateByApartmentComplexId(apartmentComplex.getId())
                        .orElse(null);
        if (previousActive != null) {
            previousActive.archive();
        }

        PatrolMap patrolMap =
                patrolMapRepository.save(
                        new PatrolMap(
                                apartmentComplex,
                                createMapName(session),
                                storedFile.publicUrl(),
                                request.getResolution(),
                                request.getOriginX(),
                                request.getOriginY(),
                                request.getOriginYaw(),
                                storedFile.width(),
                                storedFile.height()));
        apartmentComplex.assignActiveMap(patrolMap);
        session.complete(patrolMap);

        eventPublisher.publishEvent(
                new MappingStatusChangedEvent(
                        session.getId(), MappingStatus.COMPLETED, patrolMap.getId()));

        return MapUploadResponse.from(session, patrolMap);
    }

    public MapListResponse list(Long apartmentComplexId) {
        List<MapDetailResponse> maps =
                patrolMapRepository.findAllByApartmentComplexIdOrderByIdDesc(apartmentComplexId)
                        .stream()
                        .sorted(
                                Comparator.comparing((PatrolMap map) -> !map.isActive())
                                        .thenComparing(PatrolMap::getId, Comparator.reverseOrder()))
                        .map(MapDetailResponse::from)
                        .toList();
        Long activeMapId =
                patrolMapRepository
                        .findByApartmentComplexId(apartmentComplexId)
                        .map(PatrolMap::getId)
                        .orElse(null);
        return MapListResponse.builder().maps(maps).activeMapId(activeMapId).build();
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

    @Transactional
    public MapDetailResponse activate(Long apartmentComplexId, Long mapId) {
        navigationConfigurationGuard.assertMutable(apartmentComplexId);

        PatrolMap target =
                patrolMapRepository
                        .findForUpdateByIdAndApartmentComplexId(mapId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));

        if (target.isActive()) {
            return MapDetailResponse.from(target);
        }

        PatrolMap currentActive =
                patrolMapRepository
                        .findForUpdateByApartmentComplexId(apartmentComplexId)
                        .orElse(null);
        if (currentActive != null) {
            currentActive.archive();
        }

        target.activate();
        target.getApartmentComplex().assignActiveMap(target);
        return MapDetailResponse.from(target);
    }

    @Transactional
    public void delete(Long apartmentComplexId, Long mapId) {
        PatrolMap patrolMap =
                patrolMapRepository
                        .findForUpdateByIdAndApartmentComplexId(mapId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));

        if (patrolMap.getStatus() == MapStatus.ACTIVE) {
            throw new BusinessException(ErrorCode.MAP_ACTIVE_CANNOT_DELETE);
        }
        if (patrolRepository.existsByMapId(mapId)) {
            throw new BusinessException(ErrorCode.MAP_REFERENCED_BY_PATROL);
        }

        navigationWaypointRepository.deleteAllByPatrolMapId(mapId);
        patrolCheckpointVisitRepository.deleteAllByCheckpointPatrolMapId(mapId);
        checkpointRepository.deleteAllByPatrolMapId(mapId);
        mappingSessionRepository.clearResultMapId(mapId);

        String mapUrl = patrolMap.getUrl();
        patrolMapRepository.delete(patrolMap);

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        mapFileStorage.deleteByUrl(mapUrl);
                    }
                });
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

    private void registerRollbackFileCleanup(String newMapUrl) {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCompletion(int status) {
                        if (status != STATUS_COMMITTED) {
                            mapFileStorage.deleteByUrl(newMapUrl);
                        }
                    }
                });
    }
}
