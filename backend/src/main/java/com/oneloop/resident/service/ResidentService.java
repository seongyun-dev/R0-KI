package com.oneloop.resident.service;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.response.PageResponse;
import com.oneloop.notification.domain.Notification;
import com.oneloop.notification.repository.NotificationRepository;
import com.oneloop.notification.repository.ResidentLastNotificationProjection;
import com.oneloop.resident.domain.RegisteredVehicle;
import com.oneloop.resident.domain.Resident;
import com.oneloop.resident.dto.request.ResidentNotificationUpdateRequest;
import com.oneloop.resident.dto.request.ResidentRegisterRequest;
import com.oneloop.resident.dto.request.ResidentUpdateRequest;
import com.oneloop.resident.dto.request.VehicleRegisterRequest;
import com.oneloop.resident.dto.response.RegisteredVehicleResponse;
import com.oneloop.resident.dto.response.ResidentDetailResponse;
import com.oneloop.resident.dto.response.ResidentFilterOptionsResponse;
import com.oneloop.resident.dto.response.ResidentListResponse;
import com.oneloop.resident.dto.response.ResidentNotificationHistoryResponse;
import com.oneloop.resident.dto.response.ResidentSummaryResponse;
import com.oneloop.resident.repository.RegisteredVehicleRepository;
import com.oneloop.resident.repository.ResidentRepository;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 입주민과 등록 차량을 관리한다.
 *
 * <p>불법주차 SMS는 등록 차량이 있는 세대에만 나간다(EventCreationService 참고). 즉 여기서 관리하는 데이터가 알림 발송의 전제조건이다.
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ResidentService {

    // 입주민 상세에 함께 내려주는 최근 알림 이력 건수
    private static final int RECENT_NOTIFICATION_SIZE = 5;

    private final ResidentRepository residentRepository;
    private final RegisteredVehicleRepository registeredVehicleRepository;
    private final NotificationRepository notificationRepository;
    private final DetectedEventRepository detectedEventRepository;
    private final ApartmentComplexRepository apartmentComplexRepository;

    /**
     * 로그인한 관리자의 소속 단지에 입주민을 등록한다. 차량은 함께 등록할 수도 있고, 등록 후 상세에서 따로 추가할 수도 있다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param request 입주민 정보와 등록 차량 목록
     * @return 등록된 입주민 요약
     * @throws BusinessException 같은 동·호수·연락처가 이미 있거나, 차량 번호가 이미 등록된 경우
     */
    @Transactional
    public ResidentSummaryResponse register(
            Long apartmentComplexId, ResidentRegisterRequest request) {
        if (residentRepository
                .existsByApartmentComplexIdAndBuildingNumberAndUnitNumberAndPhoneNumber(
                        apartmentComplexId,
                        request.getBuildingNumber(),
                        request.getUnitNumber(),
                        request.getPhoneNumber())) {
            throw new BusinessException(ErrorCode.RESIDENT_ALREADY_EXISTS);
        }

        List<VehicleRegisterRequest> vehicleRequests =
                request.getVehicles() == null ? List.of() : request.getVehicles();
        validateNewLicensePlates(vehicleRequests);

        ApartmentComplex apartmentComplex =
                apartmentComplexRepository.getReferenceById(apartmentComplexId);
        Resident resident =
                residentRepository.save(
                        new Resident(
                                apartmentComplex,
                                request.getName(),
                                request.getPhoneNumber(),
                                request.getBuildingNumber(),
                                request.getUnitNumber()));

        vehicleRequests.forEach(
                vehicle ->
                        registeredVehicleRepository.save(
                                new RegisteredVehicle(
                                        resident,
                                        vehicle.getLicensePlate(),
                                        vehicle.isDisabledVehicle())));

        return ResidentSummaryResponse.from(resident);
    }

    /**
     * 로그인한 관리자의 소속 단지 입주민 목록을 조회한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param keyword 이름·연락처·차량번호 부분 검색어 (비어 있으면 전체)
     * @param buildingNumber 동 필터 (비어 있으면 전체)
     * @param notificationEnabled 알림 수신 여부 필터 (null이면 전체)
     * @param pageable 페이지 정보
     * @return 입주민 페이지 목록
     */
    public PageResponse<ResidentListResponse> findAll(
            Long apartmentComplexId,
            String keyword,
            String buildingNumber,
            Boolean notificationEnabled,
            Pageable pageable) {
        Page<Resident> residents =
                residentRepository.findAllByFilter(
                        apartmentComplexId,
                        blankToNull(keyword),
                        blankToNull(buildingNumber),
                        notificationEnabled,
                        pageable);

        List<Long> residentIds = residents.stream().map(Resident::getId).toList();
        Map<Long, List<RegisteredVehicle>> vehiclesByResidentId =
                findVehiclesByResidentId(residentIds);
        Map<Long, LocalDateTime> lastNotifiedAtByResidentId = findLastNotifiedAt(residentIds);

        return PageResponse.from(
                residents.map(
                        resident ->
                                ResidentListResponse.of(
                                        resident,
                                        vehiclesByResidentId.getOrDefault(
                                                resident.getId(), List.of()),
                                        lastNotifiedAtByResidentId.get(resident.getId()))));
    }

    /**
     * 목록 필터 UI에 채울 동 목록을 조회한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @return 단지에 등록된 동 목록
     */
    public ResidentFilterOptionsResponse findFilterOptions(Long apartmentComplexId) {
        return ResidentFilterOptionsResponse.from(
                residentRepository.findDistinctBuildingNumbers(apartmentComplexId));
    }

    /**
     * 입주민 하나를 상세 조회한다. 등록 차량, 알림 이력 미리보기, 위반 이력 요약을 함께 반환한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param residentId 조회할 입주민 식별자
     * @return 입주민 상세 정보
     * @throws BusinessException 해당 단지에 그 입주민이 없는 경우
     */
    public ResidentDetailResponse findDetail(Long apartmentComplexId, Long residentId) {
        Resident resident = getResident(apartmentComplexId, residentId);
        List<RegisteredVehicle> vehicles =
                registeredVehicleRepository.findAllByResidentIdOrderByIdAsc(residentId);

        Page<Notification> recentNotifications =
                notificationRepository
                        .findAllByRecipientIdAndRecipientApartmentComplexIdOrderByIdDesc(
                                residentId,
                                apartmentComplexId,
                                PageRequest.of(0, RECENT_NOTIFICATION_SIZE));

        return ResidentDetailResponse.of(
                resident,
                vehicles,
                recentNotifications.getTotalElements(),
                countViolations(apartmentComplexId, vehicles),
                recentNotifications.stream()
                        .map(ResidentNotificationHistoryResponse::from)
                        .toList());
    }

    /**
     * 입주민에게 발송된 알림 이력을 최신순으로 조회한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param residentId 조회할 입주민 식별자
     * @param pageable 페이지 정보
     * @return 알림 이력 페이지 목록
     * @throws BusinessException 해당 단지에 그 입주민이 없는 경우
     */
    public PageResponse<ResidentNotificationHistoryResponse> findNotifications(
            Long apartmentComplexId, Long residentId, Pageable pageable) {
        getResident(apartmentComplexId, residentId);

        return PageResponse.from(
                notificationRepository
                        .findAllByRecipientIdAndRecipientApartmentComplexIdOrderByIdDesc(
                                residentId, apartmentComplexId, pageable)
                        .map(ResidentNotificationHistoryResponse::from));
    }

    /**
     * 입주민의 이름·연락처·동·호수를 수정한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param residentId 수정할 입주민 식별자
     * @param request 새 입주민 정보
     * @return 수정된 입주민 요약
     * @throws BusinessException 입주민이 없거나, 바꾼 동·호수·연락처가 다른 입주민과 겹치는 경우
     */
    @Transactional
    public ResidentSummaryResponse update(
            Long apartmentComplexId, Long residentId, ResidentUpdateRequest request) {
        Resident resident = getResident(apartmentComplexId, residentId);

        if (residentRepository
                .existsByApartmentComplexIdAndBuildingNumberAndUnitNumberAndPhoneNumberAndIdNot(
                        apartmentComplexId,
                        request.getBuildingNumber(),
                        request.getUnitNumber(),
                        request.getPhoneNumber(),
                        residentId)) {
            throw new BusinessException(ErrorCode.RESIDENT_ALREADY_EXISTS);
        }

        resident.changeInfo(
                request.getName(),
                request.getPhoneNumber(),
                request.getBuildingNumber(),
                request.getUnitNumber());
        // updatedAt(@LastModifiedDate)은 flush 시점에 갱신되므로, 응답에 반영하려면 명시적으로 flush한다.
        residentRepository.flush();
        return ResidentSummaryResponse.from(resident);
    }

    /**
     * 입주민의 알림 수신 여부를 변경한다. false로 두면 불법주차가 감지돼도 SMS가 발송되지 않는다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param residentId 변경할 입주민 식별자
     * @param request 새 알림 수신 여부
     * @return 변경된 입주민 요약
     * @throws BusinessException 해당 단지에 그 입주민이 없는 경우
     */
    @Transactional
    public ResidentSummaryResponse changeNotificationEnabled(
            Long apartmentComplexId, Long residentId, ResidentNotificationUpdateRequest request) {
        Resident resident = getResident(apartmentComplexId, residentId);

        resident.changeNotificationEnabled(request.getNotificationEnabled());
        residentRepository.flush();
        return ResidentSummaryResponse.from(resident);
    }

    /**
     * 입주민에게 차량을 추가 등록한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param residentId 차량을 등록할 입주민 식별자
     * @param request 차량 번호와 장애인 차량 여부
     * @return 등록된 차량 정보
     * @throws BusinessException 입주민이 없거나, 차량 번호가 이미 등록된 경우
     */
    @Transactional
    public RegisteredVehicleResponse addVehicle(
            Long apartmentComplexId, Long residentId, VehicleRegisterRequest request) {
        Resident resident = getResident(apartmentComplexId, residentId);

        if (registeredVehicleRepository.existsByLicensePlate(request.getLicensePlate())) {
            throw new BusinessException(ErrorCode.RESIDENT_VEHICLE_DUPLICATE);
        }

        RegisteredVehicle vehicle =
                registeredVehicleRepository.save(
                        new RegisteredVehicle(
                                resident, request.getLicensePlate(), request.isDisabledVehicle()));
        return RegisteredVehicleResponse.from(vehicle);
    }

    /**
     * 입주민의 등록 차량을 삭제한다. 차량을 참조하는 기록이 없어(이벤트는 번호판 문자열만 보관) 실제 row를 지운다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param residentId 차량 소유 입주민 식별자
     * @param vehicleId 삭제할 차량 식별자
     * @return 삭제된 차량 정보
     * @throws BusinessException 입주민이 없거나, 그 입주민의 차량이 아닌 경우
     */
    @Transactional
    public RegisteredVehicleResponse deleteVehicle(
            Long apartmentComplexId, Long residentId, Long vehicleId) {
        getResident(apartmentComplexId, residentId);

        RegisteredVehicle vehicle =
                registeredVehicleRepository
                        .findByIdAndResidentId(vehicleId, residentId)
                        .orElseThrow(
                                () -> new BusinessException(ErrorCode.RESIDENT_VEHICLE_NOT_FOUND));

        RegisteredVehicleResponse response = RegisteredVehicleResponse.from(vehicle);
        registeredVehicleRepository.delete(vehicle);
        return response;
    }

    // 로그인한 관리자의 단지에 속한 입주민만 꺼낸다
    private Resident getResident(Long apartmentComplexId, Long residentId) {
        return residentRepository
                .findByIdAndApartmentComplexId(residentId, apartmentComplexId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESIDENT_NOT_FOUND));
    }

    // 등록 요청 안에서의 중복과 이미 저장된 번호와의 중복을 모두 막는다
    private void validateNewLicensePlates(List<VehicleRegisterRequest> vehicles) {
        Set<String> seen = new HashSet<>();
        for (VehicleRegisterRequest vehicle : vehicles) {
            if (!seen.add(vehicle.getLicensePlate())
                    || registeredVehicleRepository.existsByLicensePlate(
                            vehicle.getLicensePlate())) {
                throw new BusinessException(ErrorCode.RESIDENT_VEHICLE_DUPLICATE);
            }
        }
    }

    // 페이지에 담긴 입주민들의 차량을 IN 쿼리 한 번으로 모아 입주민별로 묶는다
    private Map<Long, List<RegisteredVehicle>> findVehiclesByResidentId(List<Long> residentIds) {
        if (residentIds.isEmpty()) {
            return Map.of();
        }
        return registeredVehicleRepository.findAllByResidentIdInOrderByIdAsc(residentIds).stream()
                .collect(Collectors.groupingBy(vehicle -> vehicle.getResident().getId()));
    }

    // 페이지에 담긴 입주민들의 마지막 알림 발송 시각을 그룹 쿼리 한 번으로 모은다
    private Map<Long, LocalDateTime> findLastNotifiedAt(List<Long> residentIds) {
        if (residentIds.isEmpty()) {
            return Map.of();
        }
        return notificationRepository.findLastSentAtByResidentIds(residentIds).stream()
                .filter(projection -> projection.getLastSentAt() != null)
                .collect(
                        Collectors.toMap(
                                ResidentLastNotificationProjection::getResidentId,
                                ResidentLastNotificationProjection::getLastSentAt,
                                (first, ignored) -> first));
    }

    // 등록 차량 번호로 감지된 이벤트 수. 등록 차량이 없으면 IN 절이 비므로 조회하지 않는다.
    private long countViolations(Long apartmentComplexId, List<RegisteredVehicle> vehicles) {
        if (vehicles.isEmpty()) {
            return 0L;
        }
        List<String> licensePlates =
                vehicles.stream().map(RegisteredVehicle::getLicensePlate).toList();
        return detectedEventRepository.countByApartmentComplexIdAndLicensePlateIn(
                apartmentComplexId, licensePlates);
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
