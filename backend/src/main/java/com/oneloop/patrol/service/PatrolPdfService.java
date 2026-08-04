package com.oneloop.patrol.service;

import com.oneloop.patrol.dto.response.PatrolAiSummaryResponse;
import com.oneloop.map.service.MapFileStorage;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.response.PatrolBatteryResponse;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.dto.response.PatrolRouteCheckpointResponse;
import com.oneloop.patrol.dto.response.PatrolTimelineResponse;
import com.openhtmltopdf.pdfboxout.PdfRendererBuilder;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Base64;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class PatrolPdfService {

    private static final DateTimeFormatter DATE_TIME_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy.MM.dd HH:mm:ss");
    private static final String FONT_RESOURCE = "/fonts/NanumGothic-Regular.ttf";

    private final PatrolService patrolService;
    private final MapFileStorage mapFileStorage;

    public byte[] generate(Long apartmentComplexId, Long patrolId) {
        PatrolDetailResponse detail = patrolService.findDetail(apartmentComplexId, patrolId);
        String html = buildHtml(patrolId, detail);

        try (ByteArrayOutputStream output = new ByteArrayOutputStream();
                InputStream font = getClass().getResourceAsStream(FONT_RESOURCE)) {
            if (font == null) {
                throw new IllegalStateException("PDF 한글 폰트를 찾을 수 없습니다.");
            }

            PdfRendererBuilder builder = new PdfRendererBuilder();
            builder.useFastMode();
            builder.useFont(() -> getClass().getResourceAsStream(FONT_RESOURCE), "Nanum Gothic");
            builder.withHtmlContent(html, null);
            builder.toStream(output);
            builder.run();
            return output.toByteArray();
        } catch (Exception exception) {
            throw new IllegalStateException("순찰 보고서 PDF 생성에 실패했습니다.", exception);
        }
    }

    private String buildHtml(Long patrolId, PatrolDetailResponse detail) {
        StringBuilder html = new StringBuilder();
        html.append(
                """
                <!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8" />
                <style>
                  @page { size: A4; margin: 15mm 14mm 16mm; @bottom-right { content: counter(page) " / " counter(pages); font-size: 9px; color: #64748b; } }
                  * { box-sizing: border-box; }
                  body { margin: 0; font-family: 'Nanum Gothic'; color: #172033; font-size: 10px; line-height: 1.55; }
                  h1 { margin: 0; font-size: 23px; letter-spacing: -0.5px; }
                  h2 { margin: 0 0 8px; font-size: 14px; color: #132a58; }
                  .header { border-bottom: 3px solid #2563eb; padding-bottom: 12px; margin-bottom: 16px; }
                  .meta { color: #64748b; margin-top: 4px; }
                  .section { margin-top: 16px; break-inside: avoid; }
                  .summary { width: 100%; border-collapse: separate; border-spacing: 8px 0; margin-left: -8px; }
                  .summary td { width: 25%; padding: 10px; background: #f1f5f9; border-radius: 5px; vertical-align: top; }
                  .label { color: #64748b; font-size: 9px; }
                  .value { margin-top: 3px; font-weight: bold; font-size: 12px; }
                  table.data { width: 100%; border-collapse: collapse; }
                  table.data thead { display: table-header-group; }
                  table.data th { padding: 7px; background: #e8eef9; color: #243b66; text-align: left; border: 1px solid #ccd6e8; }
                  table.data td { padding: 7px; border: 1px solid #dce3ee; vertical-align: top; }
                  table.data tr { break-inside: avoid; }
                  .ai { padding: 12px; background: #f8fafc; border-left: 4px solid #2563eb; white-space: pre-wrap; }
                  .map { width: 100%; max-height: 270px; object-fit: contain; border: 1px solid #dce3ee; }
                  .empty { color: #94a3b8; padding: 10px 0; }
                </style></head><body>
                """);

        html.append("<div class='header'><h1>순찰 결과 보고서</h1><div class='meta'>보고서 번호: PATROL-")
                .append(patrolId)
                .append("</div></div>");
        appendSummary(html, detail);
        appendMap(html, mapDataUri(detail.getMapUrl()));
        appendRoute(html, detail.getRoute());
        appendTimeline(html, detail.getTimeline());
        appendAiSummary(html, detail.getAiSummary());
        return html.append("</body></html>").toString();
    }

    private void appendSummary(StringBuilder html, PatrolDetailResponse detail) {
        PatrolBatteryResponse battery = detail.getBattery();
        html.append("<table class='summary'><tr>")
                .append(summaryCell("로봇", detail.getRobotName()))
                .append(summaryCell("상태", patrolStatusLabel(detail.getPatrolStatus())))
                .append(summaryCell("순찰 시작", format(detail.getStartedAt())))
                .append(summaryCell("순찰 종료", format(detail.getEndedAt())))
                .append("</tr></table><table class='summary' style='margin-top:8px'><tr>")
                .append(summaryCell("총 순찰 시간", duration(detail.getTotalDurationMinutes())))
                .append(
                        summaryCell(
                                "시작 배터리",
                                batteryLevel(battery == null ? null : battery.getStartLevel())))
                .append(
                        summaryCell(
                                "종료 배터리",
                                batteryLevel(battery == null ? null : battery.getEndLevel())))
                .append(summaryCell("감지 이벤트", size(detail.getTimeline()) + "건"))
                .append("</tr></table>");
    }

    private void appendMap(StringBuilder html, String mapDataUri) {
        if (mapDataUri == null) return;
        html.append("<div class='section'><h2>순찰 지도</h2><img class='map' src='")
                .append(mapDataUri)
                .append("' /></div>");
    }

    private String mapDataUri(String mapUrl) {
        if (mapUrl == null || mapUrl.isBlank()) return null;
        try (InputStream input = mapFileStorage.loadByUrl(mapUrl).getInputStream()) {
            return "data:image/png;base64," + Base64.getEncoder().encodeToString(input.readAllBytes());
        } catch (Exception exception) {
            return null;
        }
    }

    private void appendRoute(StringBuilder html, List<PatrolRouteCheckpointResponse> route) {
        html.append("<div class='section'><h2>방문 경로</h2>");
        if (route == null || route.isEmpty()) {
            html.append("<div class='empty'>방문 지점 기록이 없습니다.</div></div>");
            return;
        }
        html.append(
                "<table class='data'><thead><tr><th style='width:18%'>순서</th><th>체크포인트</th></tr></thead><tbody>");
        for (PatrolRouteCheckpointResponse checkpoint : route) {
            html.append("<tr><td>")
                    .append(checkpoint.getSequence())
                    .append("</td><td>")
                    .append(escape(checkpoint.getCheckpointName()))
                    .append("</td></tr>");
        }
        html.append("</tbody></table></div>");
    }

    private void appendTimeline(StringBuilder html, List<PatrolTimelineResponse> timeline) {
        html.append("<div class='section'><h2>감지 이벤트</h2>");
        if (timeline == null || timeline.isEmpty()) {
            html.append("<div class='empty'>감지된 이벤트가 없습니다.</div></div>");
            return;
        }
        html.append(
                "<table class='data'><thead><tr><th>발생 시각</th><th>위치</th><th>유형</th><th>처리 상태</th></tr></thead><tbody>");
        for (PatrolTimelineResponse event : timeline) {
            html.append("<tr><td>")
                    .append(format(event.getRecordedAt()))
                    .append("</td><td>")
                    .append(escape(event.getCheckpointName()))
                    .append("</td><td>")
                    .append(escape(eventTypeLabel(event.getEventType())))
                    .append("</td><td>")
                    .append(escape(processingStatusLabel(event.getProcessingStatus())))
                    .append("</td></tr>");
        }
        html.append("</tbody></table></div>");
    }

    private void appendAiSummary(StringBuilder html, PatrolAiSummaryResponse aiSummary) {
        html.append("<div class='section'><h2>AI 순찰 요약</h2><div class='ai'>");
        String content = aiSummary == null ? null : aiSummary.getSummaryContent();
        html.append(content == null || content.isBlank() ? "생성된 AI 요약이 없습니다." : escape(content));
        html.append("</div></div>");
    }

    private String summaryCell(String label, String value) {
        return "<td><div class='label'>"
                + escape(label)
                + "</div><div class='value'>"
                + escape(value)
                + "</div></td>";
    }

    private String format(LocalDateTime value) {
        return value == null ? "-" : value.format(DATE_TIME_FORMATTER);
    }

    private String duration(Integer minutes) {
        return minutes == null ? "-" : minutes + "분";
    }

    private String batteryLevel(BigDecimal level) {
        return level == null ? "-" : level.stripTrailingZeros().toPlainString() + "%";
    }

    private int size(List<?> values) {
        return values == null ? 0 : values.size();
    }

    // enum 이름을 그대로 출력하면 COMPLETED처럼 영문으로 보이므로 보고서 전용 한글 표시명으로 변환한다.
    private String patrolStatusLabel(PatrolStatus status) {
        if (status == null) return "-";
        return switch (status) {
            case IN_PROGRESS -> "순찰 중";
            case STOP_REQUESTED -> "종료 요청 중";
            case COMPLETED -> "완료";
            case STOPPED -> "중단";
            case FAILED -> "실패";
        };
    }

    private String eventTypeLabel(EventType type) {
        if (type == null) return "-";
        return switch (type) {
            case ILLEGAL_PARKING -> "불법 주차";
            case UNREGISTERED_VEHICLE -> "미등록 차량";
            case TRASH_DETECTED -> "쓰레기 감지";
            case RECYCLING_AREA_FULL -> "재활용 구역 포화";
            case EMERGENCY -> "응급 상황";
        };
    }

    private String processingStatusLabel(ProcessingStatus status) {
        if (status == null) return "-";
        return switch (status) {
            case DETECTED -> "감지";
            case PROCESSING -> "처리 중";
            case COMPLETED -> "처리 완료";
        };
    }

    private String escape(String value) {
        if (value == null || value.isBlank() || "null".equals(value)) return "-";
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }

}
