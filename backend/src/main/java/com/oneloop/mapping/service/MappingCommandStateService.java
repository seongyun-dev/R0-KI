package com.oneloop.mapping.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.domain.MappingStopCommandStatus;
import com.oneloop.mapping.dto.mqtt.StartMappingCommand;
import com.oneloop.mapping.dto.mqtt.StopMappingCommand;
import com.oneloop.mapping.dto.request.MappingStartRequest;
import com.oneloop.mapping.dto.response.MappingStartResponse;
import com.oneloop.mapping.dto.response.MappingStopResponse;
import com.oneloop.mapping.event.MappingStatusChangedEvent;
import com.oneloop.mapping.event.MappingStopCommandStatusChangedEvent;
import com.oneloop.mapping.repository.MappingSessionRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** START_MAPPING 명령을 발행하기 전에 세션과 commandId를 독립 트랜잭션으로 확정한다. */
@Service
@RequiredArgsConstructor
public class MappingCommandStateService {

    private static final List<MappingStatus> ACTIVE_STATUSES =
            List.of(MappingStatus.REQUESTED, MappingStatus.MAPPING);

    private final MappingSessionRepository mappingSessionRepository;
    private final RobotRepository robotRepository;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public PreparedMappingStart prepareStart(
            Long apartmentComplexId, MappingStartRequest request) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                request.getRobotId(), apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        String commandId = UUID.randomUUID().toString();
        List<MappingSession> existingSessions =
                List.copyOf(
                        mappingSessionRepository.findForUpdateByApartmentComplexIdOrRobotId(
                                apartmentComplexId, robot.getId()));
        MappingSession session;
        if (existingSessions.isEmpty()) {
            session =
                    mappingSessionRepository.save(
                            new MappingSession(robot.getApartmentComplex(), robot, commandId));
        } else {
            if (existingSessions.size() != 1) {
                throw new BusinessException(ErrorCode.MAPPING_SESSION_ALREADY_EXISTS);
            }
            session = existingSessions.getFirst();
            boolean sameApartment =
                    Objects.equals(session.getApartmentComplex().getId(), apartmentComplexId);
            boolean sameRobot = Objects.equals(session.getRobot().getId(), robot.getId());
            if (!sameApartment || !sameRobot) {
                throw new BusinessException(ErrorCode.MAPPING_SESSION_ALREADY_EXISTS);
            }
            if (ACTIVE_STATUSES.contains(session.getStatus())) {
                throw new BusinessException(ErrorCode.MAPPING_SESSION_ALREADY_ACTIVE);
            }
            session.restart(commandId);
        }
        StartMappingCommand command = StartMappingCommand.of(commandId, session.getId());
        return new PreparedMappingStart(
                session.getId(),
                commandId,
                robot.getSerialNumber(),
                command,
                MappingStartResponse.from(session));
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void failStartPublish(Long mappingSessionId, String commandId) {
        mappingSessionRepository
                .findById(mappingSessionId)
                .filter(
                        session ->
                                session.getStatus() == MappingStatus.REQUESTED
                                        && Objects.equals(session.getCommandId(), commandId))
                .ifPresent(
                        session -> {
                            session.fail();
                            eventPublisher.publishEvent(
                                    new MappingStatusChangedEvent(
                                            session.getId(), MappingStatus.FAILED));
                        });
    }

    @Transactional
    public PreparedMappingStop prepareStop(Long apartmentComplexId, Long mappingSessionId) {
        MappingSession session =
                mappingSessionRepository
                        .findForUpdateByIdAndApartmentComplexId(
                                mappingSessionId, apartmentComplexId)
                        .orElseThrow(
                                () ->
                                        new BusinessException(
                                                ErrorCode.MAPPING_SESSION_NOT_FOUND));

        if (session.getStatus() != MappingStatus.MAPPING) {
            throw new BusinessException(ErrorCode.MAPPING_SESSION_INVALID_STATE);
        }

        boolean shouldPublish = false;
        if (session.getStopCommandId() == null) {
            session.prepareStop(UUID.randomUUID().toString());
            shouldPublish = true;
        } else if (session.getStopCommandStatus() == MappingStopCommandStatus.PUBLISH_FAILED) {
            shouldPublish = true;
        }

        StopMappingCommand command =
                StopMappingCommand.of(session.getStopCommandId(), session.getId());
        return new PreparedMappingStop(
                session.getId(),
                session.getStopCommandId(),
                session.getRobot().getSerialNumber(),
                command,
                shouldPublish,
                new MappingStopResponse(session.getId(), session.getStopCommandId()));
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markStopPublished(Long mappingSessionId, String commandId) {
        mappingSessionRepository
                .findById(mappingSessionId)
                .filter(session -> Objects.equals(session.getStopCommandId(), commandId))
                .filter(MappingSession::markStopPublished)
                .ifPresent(this::publishStopCommandStatusChanged);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void failStopPublish(Long mappingSessionId, String commandId, String reason) {
        mappingSessionRepository
                .findById(mappingSessionId)
                .filter(session -> Objects.equals(session.getStopCommandId(), commandId))
                .filter(session -> session.markStopPublishFailed(reason))
                .ifPresent(this::publishStopCommandStatusChanged);
    }

    private void publishStopCommandStatusChanged(MappingSession session) {
        eventPublisher.publishEvent(
                new MappingStopCommandStatusChangedEvent(
                        session.getId(),
                        session.getStatus(),
                        session.getStopCommandId(),
                        session.getStopCommandStatus(),
                        session.getStopFailureReason()));
    }

    public record PreparedMappingStart(
            Long mappingSessionId,
            String commandId,
            String robotKey,
            StartMappingCommand command,
            MappingStartResponse response) {}

    public record PreparedMappingStop(
            Long mappingSessionId,
            String commandId,
            String robotKey,
            StopMappingCommand command,
            boolean shouldPublish,
            MappingStopResponse response) {}
}
