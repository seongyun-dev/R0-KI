package com.oneloop.robot.service;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.response.PageResponse;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.response.PatrolSummaryResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.dto.request.RobotRegisterRequest;
import com.oneloop.robot.dto.request.RobotUpdateRequest;
import com.oneloop.robot.dto.response.RobotDeleteResponse;
import com.oneloop.robot.dto.response.RobotDetailResponse;
import com.oneloop.robot.dto.response.RobotListResponse;
import com.oneloop.robot.dto.response.RobotRegisterResponse;
import com.oneloop.robot.dto.response.RobotStatsResponse;
import com.oneloop.robot.dto.response.RobotUpdateResponse;
import com.oneloop.robot.repository.RobotRepository;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RobotService {

    private final RobotRepository robotRepository;
    private final ApartmentComplexRepository apartmentComplexRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final PatrolRepository patrolRepository;
    private final CheckpointLocator checkpointLocator;
    private final RobotServiceTokenPublisher robotServiceTokenPublisher;

    /**
     * 로그인한 관리자의 소속 단지에 새로운 순찰로봇을 등록한다. 등록과 동시에 로봇 전용 서비스 토큰(REST 인증용)을 발급하고,
     * MQTT retained 메시지로 로봇에 전달한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param request 로봇 이름과 시리얼 번호
     * @return 등록된 로봇 정보(서비스 토큰 포함, 이후엔 재조회 불가)
     * @throws BusinessException 시리얼 번호가 이미 등록되어 있는 경우
     */
    @Transactional
    public RobotRegisterResponse register(Long apartmentComplexId, RobotRegisterRequest request) {
        // 시리얼 번호 중복 시 등록 거부
        if (robotRepository.findBySerialNumber(request.getSerialNumber()).isPresent()) {
            throw new BusinessException(ErrorCode.ROBOT_SERIAL_NUMBER_DUPLICATE);
        }

        ApartmentComplex apartmentComplex = apartmentComplexRepository.getReferenceById(apartmentComplexId);
        PatrolRobot robot =
                new PatrolRobot(apartmentComplex, request.getName(), request.getSerialNumber());
        String serviceToken = robotServiceTokenPublisher.generate();
        robot.issueServiceToken(serviceToken);
        robotRepository.save(robot);

        robotServiceTokenPublisher.publish(robot.getSerialNumber(), serviceToken);
        return RobotRegisterResponse.from(robot);
    }

    /**
     * 로그인한 관리자의 소속 단지에 등록된 순찰로봇 목록을 조회한다. 각 로봇의 현재 좌표가 속한 체크포인트 이름을 함께 반환한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param pageable 페이지 정보
     * @return 순찰로봇 페이지 목록
     */
    public PageResponse<RobotListResponse> findAll(Long apartmentComplexId, Pageable pageable) {
        // 로그인한 관리자의 단지에 속한, 삭제되지 않은 로봇만 페이지 조회
        Page<PatrolRobot> robots =
                robotRepository.findAllByApartmentComplexIdAndStatusNot(
                        apartmentComplexId, RobotStatus.DELETED, pageable);

        // 단지의 맵과 체크포인트를 한 번만 조회해 모든 로봇에 재사용
        List<Checkpoint> checkpoints =
                patrolMapRepository
                        .findByApartmentComplexId(apartmentComplexId)
                        .map(map -> checkpointRepository.findAllByPatrolMapId(map.getId()))
                        .orElseGet(List::of);

        // 대시보드가 순찰중 로봇에서 종료 API를 호출하려면 현재 순찰 ID가 필요하다.
        // 페이지에 포함된 로봇을 한 번의 IN 쿼리로 조회해 로봇별 추가 쿼리를 피한다.
        List<Long> robotIds = robots.stream().map(PatrolRobot::getId).toList();
        Map<Long, Patrol> activePatrolByRobotId =
                robotIds.isEmpty()
                        ? Map.of()
                        : patrolRepository
                                .findAllByRobotIdInAndStatusInOrderByStartedAtDesc(
                                        robotIds,
                                        List.of(
                                                PatrolStatus.IN_PROGRESS,
                                                PatrolStatus.STOP_REQUESTED))
                                .stream()
                                .collect(
                                        Collectors.toMap(
                                                patrol -> patrol.getRobot().getId(),
                                                Function.identity(),
                                                (latest, ignored) -> latest));

        Page<RobotListResponse> responses =
                robots.map(
                        robot ->
                                RobotListResponse.of(
                                        robot,
                                        checkpointLocator.resolveLocationName(
                                                checkpoints,
                                                robot.getXCoordinate(),
                                                robot.getYCoordinate()),
                                        activePatrolByRobotId.containsKey(robot.getId())
                                                ? activePatrolByRobotId.get(robot.getId()).getId()
                                                : null));
        return PageResponse.from(responses);
    }

    /**
     * 로그인한 관리자의 소속 단지 순찰로봇 현황(전체/순찰중/대기·충전중 수)을 조회한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @return 로봇 현황 통계
     */
    public RobotStatsResponse getStats(Long apartmentComplexId) {
        long totalCount =
                robotRepository.countByApartmentComplexIdAndStatusNot(
                        apartmentComplexId, RobotStatus.DELETED);
        long patrollingCount =
                robotRepository.countByApartmentComplexIdAndStatusIn(
                        apartmentComplexId, List.of(RobotStatus.PATROLLING));
        long idleOrChargingCount =
                robotRepository.countByApartmentComplexIdAndStatusIn(
                        apartmentComplexId, List.of(RobotStatus.IDLE, RobotStatus.CHARGING));

        return RobotStatsResponse.builder()
                .totalCount(totalCount)
                .patrollingCount(patrollingCount)
                .idleOrChargingCount(idleOrChargingCount)
                .build();
    }

    /**
     * 로그인한 관리자의 소속 단지에 등록된 순찰로봇 하나를 상세 조회한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param robotId 조회할 로봇 식별자
     * @return 로봇 상세 정보
     * @throws BusinessException 해당 단지에 그 로봇이 없는 경우
     */
    public RobotDetailResponse findById(Long apartmentComplexId, Long robotId) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                robotId, apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        // 최근 순찰 기록 미리보기 5건 (조정 가능)
        List<PatrolSummaryResponse> recentPatrols =
                patrolRepository
                        .findAllByRobotIdOrderByStartedAtDesc(robotId, PageRequest.of(0, 5))
                        .map(PatrolSummaryResponse::from)
                        .getContent();

        return RobotDetailResponse.from(robot, calculateWeeklyOperationRate(robotId), recentPatrols);
    }

    /**
     * 로그인한 관리자의 소속 단지에 등록된 순찰로봇의 이름을 수정한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param robotId 수정할 로봇 식별자
     * @param request 새 로봇 이름
     * @return 수정된 로봇 정보
     * @throws BusinessException 해당 단지에 그 로봇이 없는 경우
     */
    @Transactional
    public RobotUpdateResponse update(Long apartmentComplexId, Long robotId, RobotUpdateRequest request) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                robotId, apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        robot.rename(request.getName());
        // updatedAt(@LastModifiedDate)은 flush 시점에 갱신되므로, 응답에 반영하려면 명시적으로 flush한다.
        robotRepository.flush();
        return RobotUpdateResponse.from(robot);
    }

    /**
     * 로그인한 관리자의 소속 단지에 등록된 순찰로봇을 삭제(소프트 딜리트)한다. 순찰/탐지이벤트 기록과의 FK 무결성을 위해 실제 row는
     * 지우지 않고 상태만 DELETED로 바꾸며, 이후 목록/통계/조회 API에서는 제외된다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param robotId 삭제할 로봇 식별자
     * @return 삭제된 로봇 정보
     * @throws BusinessException 해당 단지에 그 로봇이 없는 경우
     */
    @Transactional
    public RobotDeleteResponse delete(Long apartmentComplexId, Long robotId) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                robotId, apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        robot.delete();
        // updatedAt(@LastModifiedDate)은 flush 시점에 갱신되므로, 응답에 반영하려면 명시적으로 flush한다.
        robotRepository.flush();
        return RobotDeleteResponse.from(robot);
    }

    // 이번 주(월요일 0시)가 시작된 이후 지금까지 경과한 시간 대비, 그동안 순찰한 시간의 비율(%)을 계산한다.
    private double calculateWeeklyOperationRate(Long robotId) {
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime weekStart =
                now.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)).toLocalDate().atStartOfDay();

        long elapsedSeconds = Duration.between(weekStart, now).getSeconds();
        if (elapsedSeconds <= 0) {
            return 0.0;
        }

        long activeSeconds =
                patrolRepository.findAllByRobotIdAndStartedAtGreaterThanEqual(robotId, weekStart).stream()
                        .mapToLong(patrol -> patrolActiveSeconds(patrol, now))
                        .sum();

        return Math.min(100.0, Math.round((activeSeconds * 1000.0 / elapsedSeconds)) / 10.0);
    }

    // 완료된 순찰은 저장된 총 소요시간을, 진행중인 순찰은 시작 시각부터 지금까지의 경과시간을 사용한다.
    private long patrolActiveSeconds(Patrol patrol, LocalDateTime now) {
        if (patrol.getTotalDuration() != null) {
            return patrol.getTotalDuration();
        }
        return Duration.between(patrol.getStartedAt(), now).getSeconds();
    }
}
