package com.oneloop.robot.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.dto.request.RobotRegisterRequest;
import com.oneloop.robot.dto.response.RobotResponse;
import com.oneloop.robot.repository.PatrolRobotRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RobotService {

    private final PatrolRobotRepository patrolRobotRepository;

    /**
     * 새로운 순찰로봇을 등록한다.
     *
     * @param request 로봇 이름과 시리얼 번호
     * @return 등록된 로봇 정보
     * @throws BusinessException 시리얼 번호가 이미 등록되어 있는 경우
     */
    @Transactional
    public RobotResponse register(RobotRegisterRequest request) {
        // 이미 등록된 로봇일 경우, 예외처리
        if (patrolRobotRepository.findBySerialNumber(request.getSerialNumber()).isPresent()) {
            throw new BusinessException(ErrorCode.ROBOT_SERIAL_NUMBER_DUPLICATE);
        }

        PatrolRobot robot = new PatrolRobot(request.getName(), request.getSerialNumber());
        return RobotResponse.from(patrolRobotRepository.save(robot));
    }
}
