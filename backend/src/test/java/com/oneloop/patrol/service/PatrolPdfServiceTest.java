package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.service.MapFileStorage;
import com.oneloop.patrol.dto.response.PatrolAiSummaryResponse;
import com.oneloop.patrol.dto.response.PatrolBatteryResponse;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.dto.response.PatrolRouteCheckpointResponse;
import com.oneloop.patrol.dto.response.PatrolTimelineResponse;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.List;
import javax.imageio.ImageIO;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.rendering.ImageType;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.apache.pdfbox.text.PDFTextStripper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PatrolPdfServiceTest {

    @Mock private PatrolService patrolService;
    @Mock private MapFileStorage mapFileStorage;
    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private CheckpointRepository checkpointRepository;
    @Mock private PatrolMapRenderer patrolMapRenderer;

    @Test
    void generatesKoreanPatrolReport() throws Exception {
        Long apartmentComplexId = 10L;
        Long patrolId = 42L;
        PatrolDetailResponse detail =
                PatrolDetailResponse.builder()
                        .robotName("R-01 순찰 로봇")
                        .patrolStatus(PatrolStatus.COMPLETED)
                        .startedAt(LocalDateTime.of(2026, 8, 4, 9, 0))
                        .endedAt(LocalDateTime.of(2026, 8, 4, 9, 42))
                        .totalDurationMinutes(42)
                        .battery(
                                PatrolBatteryResponse.builder()
                                        .startLevel(new BigDecimal("98"))
                                        .endLevel(new BigDecimal("76"))
                                        .build())
                        .route(
                                List.of(
                                        PatrolRouteCheckpointResponse.builder()
                                                .sequence(1)
                                                .checkpointName("정문")
                                                .build(),
                                        PatrolRouteCheckpointResponse.builder()
                                                .sequence(2)
                                                .checkpointName("지하 주차장")
                                                .build()))
                        .timeline(
                                List.of(
                                        PatrolTimelineResponse.builder()
                                                .recordedAt(LocalDateTime.of(2026, 8, 4, 9, 15))
                                                .checkpointName("지하 주차장")
                                                .eventType(EventType.ILLEGAL_PARKING)
                                                .processingStatus(ProcessingStatus.COMPLETED)
                                                .build()))
                        .aiSummary(
                                PatrolAiSummaryResponse.builder()
                                        .summaryContent(
                                                "전체 순찰 경로를 정상적으로 완료했습니다. 지하 주차장에서 확인이 필요한 이벤트 1건이 감지되었습니다.")
                                        .build())
                        .build();
        when(patrolService.findDetail(apartmentComplexId, patrolId)).thenReturn(detail);

        byte[] pdf =
                new PatrolPdfService(
                                patrolService,
                                mapFileStorage,
                                patrolMapRepository,
                                checkpointRepository,
                                patrolMapRenderer)
                        .generate(apartmentComplexId, patrolId);

        assertThat(pdf).startsWith("%PDF".getBytes());
        try (PDDocument document = PDDocument.load(pdf)) {
            String text = new PDFTextStripper().getText(document);
            assertThat(document.getNumberOfPages()).isGreaterThanOrEqualTo(1);
            assertThat(text)
                    .contains(
                            "순찰 결과 보고서",
                            "R-01 순찰 로봇",
                            "완료",
                            "지하 주차장",
                            "불법 주차",
                            "처리 완료",
                            "AI 순찰 요약")
                    .doesNotContain("COMPLETED", "ILLEGAL_PARKING");

            Path preview = Path.of("build", "test-pdfs", "patrol-report-page-1.png");
            Files.createDirectories(preview.getParent());
            ImageIO.write(
                    new PDFRenderer(document).renderImageWithDPI(0, 144, ImageType.RGB),
                    "png",
                    preview.toFile());
        }

        Path output = Path.of("build", "test-pdfs", "patrol-report-sample.pdf");
        Files.createDirectories(output.getParent());
        Files.write(output, pdf);
    }
}
