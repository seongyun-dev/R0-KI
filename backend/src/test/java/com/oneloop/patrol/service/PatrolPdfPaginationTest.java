package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import com.oneloop.map.service.MapFileStorage;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.dto.response.PatrolRouteCheckpointResponse;
import com.oneloop.patrol.dto.response.PatrolTimelineResponse;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import javax.imageio.ImageIO;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.core.io.ByteArrayResource;

/**
 * 보고서가 여러 장으로 넘어갈 때 표가 제대로 이어지는지 확인한다.
 *
 * <p>openhtmltopdf 는 CSS2.1 기반이라 최신 `break-inside` 를 무시한다. 예전에 그 속성을 쓰고 있어서 표 머리글만 남고 본문이 다음 장으로
 * 넘어가거나 행이 중간에서 잘렸다. `page-break-inside` 로 바꾼 뒤의 회귀를 막는다.
 */
@ExtendWith(MockitoExtension.class)
class PatrolPdfPaginationTest {

    private static final String EVENT_TABLE_HEADER = "발생 시각";
    private static final String EVENT_ROW_MARKER = "주차장 A";

    @Mock private PatrolService patrolService;
    @Mock private MapFileStorage mapFileStorage;
    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private CheckpointRepository checkpointRepository;
    @Mock private PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;
    @Mock private PatrolMapRenderer patrolMapRenderer;

    @Test
    void 이벤트_표가_페이지를_넘어가도_머리글만_남지_않는다() throws Exception {
        Long complexId = 11L;
        Long patrolId = 290L;
        when(patrolService.findDetail(complexId, patrolId)).thenReturn(detail());

        byte[] png = dummyMap();
        lenient().when(mapFileStorage.loadByUrl(any())).thenReturn(new ByteArrayResource(png));
        lenient()
                .when(patrolMapRepository.findByApartmentComplexId(complexId))
                .thenReturn(Optional.empty());
        lenient()
                .when(patrolMapRenderer.render(any(), any(), any(), any(), any(), any()))
                .thenReturn(png);

        byte[] pdf =
                new PatrolPdfService(
                                patrolService,
                                mapFileStorage,
                                patrolMapRepository,
                                checkpointRepository,
                                patrolCheckpointVisitRepository,
                                patrolMapRenderer)
                        .generate(complexId, patrolId);

        try (PDDocument document = PDDocument.load(pdf)) {
            assertThat(document.getNumberOfPages()).isGreaterThan(1);
            for (int page = 1; page <= document.getNumberOfPages(); page++) {
                PDFTextStripper stripper = new PDFTextStripper();
                stripper.setStartPage(page);
                stripper.setEndPage(page);
                String text = stripper.getText(document);
                if (text.contains(EVENT_TABLE_HEADER)) {
                    assertThat(text)
                            .as("%d쪽에 이벤트 표 머리글만 있고 행이 없다", page)
                            .contains(EVENT_ROW_MARKER);
                }
            }
        }
    }

    private PatrolDetailResponse detail() {
        List<PatrolTimelineResponse> timeline = new ArrayList<>();
        for (int i = 0; i < 26; i++) {
            timeline.add(
                    PatrolTimelineResponse.builder()
                            .recordedAt(LocalDateTime.of(2026, 8, 5, 20, 56).plusMinutes(i * 3L))
                            .checkpointName(EVENT_ROW_MARKER)
                            .eventId((long) i)
                            .eventType(EventType.UNREGISTERED_VEHICLE)
                            .processingStatus(ProcessingStatus.COMPLETED)
                            .build());
        }
        List<PatrolRouteCheckpointResponse> route = new ArrayList<>();
        for (int i = 1; i <= 10; i++) {
            route.add(
                    PatrolRouteCheckpointResponse.builder()
                            .sequence(i)
                            .checkpointName("구역 " + i)
                            .build());
        }
        return PatrolDetailResponse.builder()
                .robotName("RO-Ki4728")
                .patrolStatus(PatrolStatus.COMPLETED)
                .startedAt(LocalDateTime.of(2026, 8, 5, 20, 40))
                .endedAt(LocalDateTime.of(2026, 8, 5, 21, 58))
                .totalDurationMinutes(78)
                .mapUrl("/api/v1/maps/files/sample.png")
                .route(route)
                .timeline(timeline)
                .build();
    }

    private byte[] dummyMap() throws Exception {
        BufferedImage image = new BufferedImage(766, 626, BufferedImage.TYPE_INT_RGB);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        ImageIO.write(image, "png", output);
        return output.toByteArray();
    }
}
