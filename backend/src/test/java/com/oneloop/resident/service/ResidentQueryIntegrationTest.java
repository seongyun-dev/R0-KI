package com.oneloop.resident.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.RiskLevel;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.global.response.PageResponse;
import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.repository.NotificationRepository;
import com.oneloop.resident.domain.RegisteredVehicle;
import com.oneloop.resident.domain.Resident;
import com.oneloop.resident.dto.response.ResidentDetailResponse;
import com.oneloop.resident.dto.response.ResidentListResponse;
import com.oneloop.resident.repository.RegisteredVehicleRepository;
import com.oneloop.resident.repository.ResidentRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.test.context.ActiveProfiles;

/**
 * 입주민 조회 쿼리를 H2에 실제로 실행해 본다.
 *
 * <p>목록 쿼리는 DISTINCT + LEFT JOIN + CONCAT LIKE, 마지막 발송 시각은 GROUP BY 프로젝션이라 부트 시점 파싱만으로는
 * 검증되지 않는다. 차량이 여러 대인 세대가 중복 행으로 새지 않는지도 여기서 확인한다.
 */
@ActiveProfiles("test")
@SpringBootTest
class ResidentQueryIntegrationTest {

    @Autowired private ResidentService residentService;
    @Autowired private ApartmentComplexRepository apartmentComplexRepository;
    @Autowired private ResidentRepository residentRepository;
    @Autowired private RegisteredVehicleRepository registeredVehicleRepository;
    @Autowired private NotificationRepository notificationRepository;
    @Autowired private DetectedEventRepository detectedEventRepository;
    @Autowired private RobotRepository robotRepository;

    private static final PageRequest FIRST_PAGE =
            PageRequest.of(0, 20, Sort.by("buildingNumber", "unitNumber"));

    @Test
    void listsResidentsScopedToTheirOwnComplex() {
        Fixture mine = fixture("101", "1502");
        Fixture other = fixture("101", "1502");

        PageResponse<ResidentListResponse> page =
                residentService.findAll(mine.complexId(), null, null, null, FIRST_PAGE);

        assertThat(page.content()).extracting(ResidentListResponse::getResidentId)
                .containsExactly(mine.residentId())
                .doesNotContain(other.residentId());
    }

    @Test
    void findsResidentByLicensePlateWithoutDuplicatingMultiVehicleHouseholds() {
        Fixture fixture = fixture("102", "301");
        // 두 대 모두 검색어에 걸리게 해서 DISTINCT 가 없으면 같은 세대가 두 줄로 나오는 상황을 만든다
        String sharedPrefix = "77" + shortId();
        addVehicle(fixture.resident(), sharedPrefix + "가1111");
        addVehicle(fixture.resident(), sharedPrefix + "가2222");

        PageResponse<ResidentListResponse> page =
                residentService.findAll(fixture.complexId(), sharedPrefix, null, null, FIRST_PAGE);

        assertThat(page.content()).hasSize(1);
        assertThat(page.totalElements()).isEqualTo(1);
        assertThat(page.content().get(0).getVehicleCount()).isEqualTo(2);
    }

    @Test
    void findsResidentByName() {
        Fixture fixture = fixture("103", "701");

        PageResponse<ResidentListResponse> page =
                residentService.findAll(
                        fixture.complexId(), fixture.resident().getName(), null, null, FIRST_PAGE);

        assertThat(page.content()).hasSize(1);
        // 목록에서는 연락처가 마스킹돼 나가야 한다
        assertThat(page.content().get(0).getMaskedPhoneNumber()).contains("*");
    }

    @Test
    void filtersByBuildingAndNotificationEnabled() {
        ApartmentComplex complex = complex();
        Resident receiving = resident(complex, "101", "101");
        Resident blocked = resident(complex, "101", "102");
        Resident otherBuilding = resident(complex, "202", "103");
        blocked.changeNotificationEnabled(false);
        residentRepository.saveAndFlush(blocked);

        PageResponse<ResidentListResponse> inBuilding101 =
                residentService.findAll(complex.getId(), null, "101", null, FIRST_PAGE);
        assertThat(inBuilding101.content()).extracting(ResidentListResponse::getResidentId)
                .containsExactlyInAnyOrder(receiving.getId(), blocked.getId())
                .doesNotContain(otherBuilding.getId());

        PageResponse<ResidentListResponse> enabledOnly =
                residentService.findAll(complex.getId(), null, "101", true, FIRST_PAGE);
        assertThat(enabledOnly.content()).extracting(ResidentListResponse::getResidentId)
                .containsExactly(receiving.getId());

        PageResponse<ResidentListResponse> disabledOnly =
                residentService.findAll(complex.getId(), null, "101", false, FIRST_PAGE);
        assertThat(disabledOnly.content()).extracting(ResidentListResponse::getResidentId)
                .containsExactly(blocked.getId());
    }

    @Test
    void reportsLastNotifiedAtAndViolationCount() {
        Fixture fixture = fixture("104", "1201");
        DetectedEvent event = illegalParkingEvent(fixture);
        Notification notification =
                notificationRepository.save(new Notification(event, fixture.resident(), "내용"));
        // 테스트는 트랜잭션 밖이라 save 직후 엔티티가 detached 다 — 상태 변경 후 다시 저장해야 반영된다
        notification.markAsSent();
        notificationRepository.saveAndFlush(notification);

        PageResponse<ResidentListResponse> page =
                residentService.findAll(fixture.complexId(), null, "104", null, FIRST_PAGE);
        assertThat(page.content().get(0).getLastNotifiedAt()).isNotNull();

        ResidentDetailResponse detail =
                residentService.findDetail(fixture.complexId(), fixture.residentId());
        assertThat(detail.getNotificationCount()).isEqualTo(1);
        assertThat(detail.getViolationCount()).isEqualTo(1);
        assertThat(detail.getRecentNotifications()).hasSize(1);
        // 상세에서는 전체 번호를 그대로 노출한다
        assertThat(detail.getPhoneNumber()).isEqualTo(fixture.resident().getPhoneNumber());
    }

    @Test
    void leavesLastNotifiedAtNullWhenNothingWasSent() {
        Fixture fixture = fixture("105", "101");

        PageResponse<ResidentListResponse> page =
                residentService.findAll(fixture.complexId(), null, "105", null, FIRST_PAGE);

        assertThat(page.content().get(0).getLastNotifiedAt()).isNull();
    }

    @Test
    void listsDistinctBuildingNumbersOfTheComplex() {
        ApartmentComplex complex = complex();
        resident(complex, "301", "101");
        resident(complex, "301", "102");
        resident(complex, "302", "103");

        assertThat(residentService.findFilterOptions(complex.getId()).getBuildingNumbers())
                .containsExactly("301", "302");
    }

    // --- fixtures ---

    private record Fixture(ApartmentComplex complex, Resident resident) {
        Long complexId() {
            return complex.getId();
        }

        Long residentId() {
            return resident.getId();
        }
    }

    private Fixture fixture(String building, String unit) {
        ApartmentComplex complex = complex();
        return new Fixture(complex, resident(complex, building, unit));
    }

    private ApartmentComplex complex() {
        return apartmentComplexRepository.saveAndFlush(
                new ApartmentComplex("complex-" + shortId(), "address", "00000"));
    }

    private Resident resident(ApartmentComplex complex, String building, String unit) {
        return residentRepository.saveAndFlush(
                new Resident(complex, "입주민" + shortId(), "010-" + digits() + "-5678", building, unit));
    }

    private void addVehicle(Resident resident, String licensePlate) {
        registeredVehicleRepository.saveAndFlush(
                new RegisteredVehicle(resident, licensePlate, false));
    }

    private DetectedEvent illegalParkingEvent(Fixture fixture) {
        String licensePlate = "12가" + digits();
        addVehicle(fixture.resident(), licensePlate);
        PatrolRobot robot =
                robotRepository.saveAndFlush(
                        new PatrolRobot(fixture.complex(), "robot", "SN-" + shortId()));
        return detectedEventRepository.saveAndFlush(
                new DetectedEvent(
                        null,
                        robot,
                        EventType.ILLEGAL_PARKING,
                        "불법주차",
                        null,
                        new BigDecimal("0.900"),
                        LocalDateTime.now(),
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        RiskLevel.NORMAL,
                        licensePlate));
    }

    // license_plate 는 테이블 전역 unique 라 테스트끼리 겹치지 않게 매번 새 값을 만든다
    private String shortId() {
        return UUID.randomUUID().toString().substring(0, 8);
    }

    private String digits() {
        long bits = UUID.randomUUID().getLeastSignificantBits();
        return String.valueOf(1000 + (int) (Math.floorMod(bits, 9000L)));
    }
}
