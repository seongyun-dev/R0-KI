package com.oneloop.robot.dto.response;

import com.oneloop.patrol.dto.response.PatrolSummaryResponse;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.domain.SensorStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "순찰로봇 상세 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RobotDetailResponse {

    @Schema(description = "로봇 ID", example = "1")
    private Long robotId;

    @Schema(description = "로봇 이름", example = "순찰로봇 1호")
    private String robotName;

    @Schema(description = "로봇 시리얼 번호", example = "ROBOT-0001")
    private String robotSerialNumber;

    @Schema(description = "로봇 상태", example = "IDLE")
    private RobotStatus robotStatus;

    @Schema(description = "배터리 잔량(%)", example = "87.50", nullable = true)
    private BigDecimal batteryLevel;

    @Schema(
            description = "카메라 모듈 상태",
            example = "NORMAL",
            nullable = true)
    private SensorStatus cameraStatus;

    @Schema(
            description = "라이다 센서 상태",
            example = "NORMAL",
            nullable = true)
    private SensorStatus lidarStatus;

    @Schema(
            description = "휠 모터 상태",
            example = "NEEDS_INSPECTION",
            nullable = true)
    private SensorStatus motorStatus;

    @Schema(description = "등록일시")
    private LocalDateTime registeredAt;

    @Schema(description = "이번 주 가동률(%) - 이번 주 시작 이후 경과 시간 대비 순찰 시간 비율", example = "94.0")
    private double weeklyOperationRate;

    @Schema(description = "최근 순찰 기록 (최신순)")
    private List<PatrolSummaryResponse> recentPatrols;

    public static RobotDetailResponse from(
            PatrolRobot robot, double weeklyOperationRate, List<PatrolSummaryResponse> recentPatrols) {
        return RobotDetailResponse.builder()
                .robotId(robot.getId())
                .robotName(robot.getName())
                .robotSerialNumber(robot.getSerialNumber())
                .robotStatus(robot.getStatus())
                .batteryLevel(robot.getBatteryLevel())
                .cameraStatus(robot.getCameraStatus())
                .lidarStatus(robot.getLidarStatus())
                .motorStatus(robot.getMotorStatus())
                .registeredAt(robot.getCreatedAt())
                .weeklyOperationRate(weeklyOperationRate)
                .recentPatrols(recentPatrols)
                .build();
    }
}
