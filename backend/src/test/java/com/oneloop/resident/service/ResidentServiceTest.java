package com.oneloop.resident.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.notification.repository.NotificationRepository;
import com.oneloop.resident.domain.RegisteredVehicle;
import com.oneloop.resident.domain.Resident;
import com.oneloop.resident.dto.request.ResidentNotificationUpdateRequest;
import com.oneloop.resident.dto.request.ResidentRegisterRequest;
import com.oneloop.resident.dto.request.ResidentUpdateRequest;
import com.oneloop.resident.dto.request.VehicleRegisterRequest;
import com.oneloop.resident.dto.response.RegisteredVehicleResponse;
import com.oneloop.resident.dto.response.ResidentSummaryResponse;
import com.oneloop.resident.repository.RegisteredVehicleRepository;
import com.oneloop.resident.repository.ResidentRepository;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class ResidentServiceTest {

    private static final Long COMPLEX_ID = 2L;
    private static final Long RESIDENT_ID = 7L;

    @Mock private ResidentRepository residentRepository;
    @Mock private RegisteredVehicleRepository registeredVehicleRepository;
    @Mock private NotificationRepository notificationRepository;
    @Mock private DetectedEventRepository detectedEventRepository;
    @Mock private ApartmentComplexRepository apartmentComplexRepository;
    @Mock private ApartmentComplex apartmentComplex;

    private ResidentService service;
    private Resident resident;

    @BeforeEach
    void setUp() {
        service =
                new ResidentService(
                        residentRepository,
                        registeredVehicleRepository,
                        notificationRepository,
                        detectedEventRepository,
                        apartmentComplexRepository);
        resident = new Resident(apartmentComplex, "김입주", "010-1234-5678", "101", "1502");
        ReflectionTestUtils.setField(resident, "id", RESIDENT_ID);
    }

    @Test
    void registersResidentWithVehicles() {
        ResidentRegisterRequest request =
                ResidentRegisterRequest.builder()
                        .name("김입주")
                        .phoneNumber("010-1234-5678")
                        .buildingNumber("101")
                        .unitNumber("1502")
                        .vehicles(
                                List.of(
                                        VehicleRegisterRequest.builder()
                                                .licensePlate("12가3456")
                                                .disabledVehicle(false)
                                                .build()))
                        .build();
        when(apartmentComplexRepository.getReferenceById(COMPLEX_ID)).thenReturn(apartmentComplex);
        when(residentRepository.save(any(Resident.class))).thenReturn(resident);

        ResidentSummaryResponse response = service.register(COMPLEX_ID, request);

        assertThat(response.getResidentId()).isEqualTo(RESIDENT_ID);
        // 새 입주민은 알림 수신이 켜진 상태로 시작해야 불법주차 SMS가 바로 나간다
        assertThat(response.isNotificationEnabled()).isTrue();
        verify(registeredVehicleRepository).save(any(RegisteredVehicle.class));
    }

    @Test
    void rejectsRegisterWhenSameUnitAndPhoneAlreadyExists() {
        ResidentRegisterRequest request =
                ResidentRegisterRequest.builder()
                        .name("김입주")
                        .phoneNumber("010-1234-5678")
                        .buildingNumber("101")
                        .unitNumber("1502")
                        .build();
        when(residentRepository
                        .existsByApartmentComplexIdAndBuildingNumberAndUnitNumberAndPhoneNumber(
                                COMPLEX_ID, "101", "1502", "010-1234-5678"))
                .thenReturn(true);

        assertThatThrownBy(() -> service.register(COMPLEX_ID, request))
                .isInstanceOf(BusinessException.class)
                .hasFieldOrPropertyWithValue("errorCode", ErrorCode.RESIDENT_ALREADY_EXISTS);
        verify(residentRepository, never()).save(any(Resident.class));
    }

    @Test
    void rejectsRegisterWhenTheSamePlateIsRepeatedInsideOneRequest() {
        ResidentRegisterRequest request =
                ResidentRegisterRequest.builder()
                        .name("김입주")
                        .phoneNumber("010-1234-5678")
                        .buildingNumber("101")
                        .unitNumber("1502")
                        .vehicles(
                                List.of(
                                        VehicleRegisterRequest.builder()
                                                .licensePlate("12가3456")
                                                .build(),
                                        VehicleRegisterRequest.builder()
                                                .licensePlate("12가3456")
                                                .build()))
                        .build();

        assertThatThrownBy(() -> service.register(COMPLEX_ID, request))
                .isInstanceOf(BusinessException.class)
                .hasFieldOrPropertyWithValue("errorCode", ErrorCode.RESIDENT_VEHICLE_DUPLICATE);
        verify(residentRepository, never()).save(any(Resident.class));
    }

    @Test
    void updatesResidentInfo() {
        when(residentRepository.findByIdAndApartmentComplexId(RESIDENT_ID, COMPLEX_ID))
                .thenReturn(Optional.of(resident));

        ResidentSummaryResponse response =
                service.update(
                        COMPLEX_ID,
                        RESIDENT_ID,
                        ResidentUpdateRequest.builder()
                                .name("이입주")
                                .phoneNumber("010-9999-8888")
                                .buildingNumber("102")
                                .unitNumber("301")
                                .build());

        assertThat(response.getName()).isEqualTo("이입주");
        assertThat(response.getPhoneNumber()).isEqualTo("010-9999-8888");
        assertThat(response.getBuildingNumber()).isEqualTo("102");
        assertThat(response.getUnitNumber()).isEqualTo("301");
    }

    @Test
    void rejectsAccessToResidentOfAnotherComplex() {
        when(residentRepository.findByIdAndApartmentComplexId(RESIDENT_ID, COMPLEX_ID))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.findDetail(COMPLEX_ID, RESIDENT_ID))
                .isInstanceOf(BusinessException.class)
                .hasFieldOrPropertyWithValue("errorCode", ErrorCode.RESIDENT_NOT_FOUND);
    }

    @Test
    void togglesNotificationEnabled() {
        when(residentRepository.findByIdAndApartmentComplexId(RESIDENT_ID, COMPLEX_ID))
                .thenReturn(Optional.of(resident));

        ResidentSummaryResponse response =
                service.changeNotificationEnabled(
                        COMPLEX_ID,
                        RESIDENT_ID,
                        ResidentNotificationUpdateRequest.builder()
                                .notificationEnabled(false)
                                .build());

        assertThat(response.isNotificationEnabled()).isFalse();
        assertThat(resident.isNotificationEnabled()).isFalse();
    }

    @Test
    void rejectsVehicleWithPlateAlreadyRegisteredElsewhere() {
        when(residentRepository.findByIdAndApartmentComplexId(RESIDENT_ID, COMPLEX_ID))
                .thenReturn(Optional.of(resident));
        when(registeredVehicleRepository.existsByLicensePlate("12가3456")).thenReturn(true);

        assertThatThrownBy(
                        () ->
                                service.addVehicle(
                                        COMPLEX_ID,
                                        RESIDENT_ID,
                                        VehicleRegisterRequest.builder()
                                                .licensePlate("12가3456")
                                                .build()))
                .isInstanceOf(BusinessException.class)
                .hasFieldOrPropertyWithValue("errorCode", ErrorCode.RESIDENT_VEHICLE_DUPLICATE);
        verify(registeredVehicleRepository, never()).save(any(RegisteredVehicle.class));
    }

    @Test
    void deletesVehicleOfResident() {
        RegisteredVehicle vehicle = new RegisteredVehicle(resident, "12가3456", false);
        ReflectionTestUtils.setField(vehicle, "id", 55L);
        when(residentRepository.findByIdAndApartmentComplexId(RESIDENT_ID, COMPLEX_ID))
                .thenReturn(Optional.of(resident));
        when(registeredVehicleRepository.findByIdAndResidentId(55L, RESIDENT_ID))
                .thenReturn(Optional.of(vehicle));

        RegisteredVehicleResponse response = service.deleteVehicle(COMPLEX_ID, RESIDENT_ID, 55L);

        assertThat(response.getLicensePlate()).isEqualTo("12가3456");
        verify(registeredVehicleRepository).delete(vehicle);
    }

    @Test
    void rejectsDeletingVehicleThatBelongsToAnotherResident() {
        when(residentRepository.findByIdAndApartmentComplexId(RESIDENT_ID, COMPLEX_ID))
                .thenReturn(Optional.of(resident));
        when(registeredVehicleRepository.findByIdAndResidentId(55L, RESIDENT_ID))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.deleteVehicle(COMPLEX_ID, RESIDENT_ID, 55L))
                .isInstanceOf(BusinessException.class)
                .hasFieldOrPropertyWithValue("errorCode", ErrorCode.RESIDENT_VEHICLE_NOT_FOUND);
    }
}
