package com.oneloop.patrol.service;

import com.oneloop.event.domain.EventType;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.patrol.dto.response.PatrolRoutePointResponse;
import com.oneloop.patrol.dto.response.PatrolTimelineResponse;
import java.awt.AlphaComposite;
import java.awt.BasicStroke;
import java.awt.Composite;
import java.awt.Color;
import java.awt.Font;
import java.awt.FontMetrics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.color.ColorSpace;
import java.awt.geom.Ellipse2D;
import java.awt.geom.Path2D;
import java.awt.geom.Rectangle2D;
import java.awt.geom.RoundRectangle2D;
import java.awt.image.BufferedImage;
import java.awt.image.ColorConvertOp;
import java.awt.image.RescaleOp;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import javax.imageio.ImageIO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * PDF 보고서용 순찰 지도 합성기.
 *
 * <p>PDF는 openhtmltopdf(HTML → PDF)로 만드는데 SVG 플러그인이 없어서, 화면(PatrolDetail)처럼 도면 위에 SVG를 얹을 수
 * 없다. 그래서 스캔 도면 PNG 위에 구역·순찰 경로·이벤트를 Java2D로 직접 그려 한 장의 PNG로 합성한다.
 *
 * <p>좌표 변환은 화면과 같은 규칙이다 — 월드(m) → 픽셀: px = (x - originX) / resolution, py = imageHeight - (y -
 * originY) / resolution (y축은 위아래가 뒤집힌다).
 */
@Slf4j
@Component
public class PatrolMapRenderer {

    /** 인쇄 선명도를 위한 확대 배율. 원본 도면이 보통 800px 안팎이라 그대로 쓰면 글자가 뭉갠다. */
    private static final int SCALE = 2;

    /**
     * 화면(순찰 상세)과 같은 가로비. 거기서는 뷰박스를 900x450 으로 잡고 도면을 늘여 채우므로
     * (preserveAspectRatio="none"), 원본 비율 그대로 실으면 PDF 만 가로가 짧아 보인다.
     */
    private static final double TARGET_ASPECT = 900.0 / 450.0;

    /* 도면을 눌러 까는 값 — 화면의 .mapbase(grayscale(1) contrast(.78) brightness(1.16), opacity .42)와 같다.
       CSS contrast/brightness 를 1차식으로 합치면 out = in*0.78*1.16 + (0.5 - 0.5*0.78)*1.16 이다. */
    private static final float BASE_SCALE = 0.78f * 1.16f;
    private static final float BASE_OFFSET = (0.5f - 0.5f * 0.78f) * 1.16f * 255f;
    private static final float BASE_OPACITY = 0.42f;

    private static final String FONT_RESOURCE = "/fonts/NanumGothic-Regular.ttf";

    // PDF 본문 강조색(#2563eb)과 같은 계열로 맞춘다
    private static final Color ROUTE = new Color(0x25, 0x63, 0xEB);
    private static final Color ZONE_LINE = new Color(0x25, 0x63, 0xEB, 0xB0);
    private static final Color ZONE_FILL = new Color(0x25, 0x63, 0xEB, 0x1F);
    private static final Color EVENT = new Color(0xDC, 0x26, 0x26);
    private static final Color LABEL_TEXT = new Color(0x17, 0x20, 0x33);
    private static final Color CHIP_BG = new Color(0xFF, 0xFF, 0xFF, 0xE6);

    private static Font baseFont;

    /**
     * 도면 위에 구역·경로·이벤트를 얹은 PNG를 돌려준다. 지도 좌표 정보(resolution/origin)가 없거나 그리다 실패하면 원본 PNG를 그대로
     * 돌려준다 — 보고서에서 지도가 아예 사라지는 것보다 낫다.
     */
    public byte[] render(
            PatrolMap patrolMap,
            byte[] mapPng,
            List<Checkpoint> zones,
            List<PatrolRoutePointResponse> routePoints,
            List<PatrolTimelineResponse> timeline,
            Function<EventType, String> eventLabeler) {
        if (mapPng == null || mapPng.length == 0) {
            return mapPng;
        }
        if (!hasCoordinateInfo(patrolMap)) {
            log.debug("[PDF] 지도 좌표 정보가 없어 도면만 싣는다. mapId={}", patrolMap == null ? null : patrolMap.getId());
            return mapPng;
        }

        try {
            BufferedImage base = ImageIO.read(new ByteArrayInputStream(mapPng));
            if (base == null) {
                return mapPng;
            }
            // 화면과 같은 가로비로 늘여 채운다. 세로는 그만큼 눌리므로 좌표도 X/Y 따로 환산한다.
            int width = base.getWidth() * SCALE;
            int height = (int) Math.round(width / TARGET_ASPECT);

            BufferedImage canvas = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
            Graphics2D g = canvas.createGraphics();
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g.setRenderingHint(
                    RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
            g.setRenderingHint(
                    RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);

            g.setColor(Color.WHITE);
            g.fillRect(0, 0, width, height);
            Composite original = g.getComposite();
            g.setComposite(AlphaComposite.getInstance(AlphaComposite.SRC_OVER, BASE_OPACITY));
            g.drawImage(dim(base), 0, 0, width, height, null);
            g.setComposite(original);

            /* 라벨 크기는 캔버스 폭에 비례시킨다 — PDF 안에서 지도가 축소돼 실리므로
               고정 pt 로 두면 도면 크기에 따라 글자가 읽을 수 없게 작아진다. */
            float labelSize = Math.max(16f, width * 0.020f);

            /* 이벤트는 구역 안에서 탐지되므로 구역명과 이름표가 그냥 두면 겹친다.
               구역명을 먼저 놓아 자리를 기록하고, 이벤트 이름표가 그 자리를 피하게 한다. */
            List<Rectangle2D> placed = new ArrayList<>();
            Projector projector = new Projector(patrolMap, base, width, height);
            drawZones(g, projector, zones, labelSize, placed);
            drawRoute(g, projector, routePoints);
            drawEvents(g, projector, timeline, eventLabeler, labelSize, placed);
            g.dispose();

            ByteArrayOutputStream output = new ByteArrayOutputStream();
            ImageIO.write(canvas, "png", output);
            return output.toByteArray();
        } catch (Exception exception) {
            log.warn("[PDF] 순찰 지도 합성에 실패해 원본 도면을 싣는다.", exception);
            return mapPng;
        }
    }

    private boolean hasCoordinateInfo(PatrolMap patrolMap) {
        return patrolMap != null
                && patrolMap.getResolution() != null
                && patrolMap.getResolution().signum() > 0
                && patrolMap.getOriginX() != null
                && patrolMap.getOriginY() != null;
    }

    /** 도면을 화면(.mapbase)과 같은 톤으로 눌러 회색조로 만든다 */
    private BufferedImage dim(BufferedImage source) {
        BufferedImage gray =
                new BufferedImage(
                        source.getWidth(), source.getHeight(), BufferedImage.TYPE_INT_RGB);
        new ColorConvertOp(ColorSpace.getInstance(ColorSpace.CS_GRAY), null)
                .filter(source, gray);
        BufferedImage toned =
                new BufferedImage(gray.getWidth(), gray.getHeight(), BufferedImage.TYPE_INT_RGB);
        new RescaleOp(BASE_SCALE, BASE_OFFSET, null).filter(gray, toned);
        return toned;
    }

    /**
     * 월드 좌표(m) → 합성 캔버스 픽셀.
     *
     * <p>도면을 가로로 늘여 채우므로 X와 Y의 배율이 다르다. 하나로 묶으면 구역·경로가 도면과 어긋난다.
     */
    private static final class Projector {
        private final double resolution;
        private final double originX;
        private final double originY;
        private final int imageHeight;
        private final double scaleX;
        private final double scaleY;

        private Projector(PatrolMap patrolMap, BufferedImage base, int canvasW, int canvasH) {
            this.resolution = patrolMap.getResolution().doubleValue();
            this.originX = patrolMap.getOriginX().doubleValue();
            this.originY = patrolMap.getOriginY().doubleValue();
            this.imageHeight = base.getHeight();
            this.scaleX = (double) canvasW / base.getWidth();
            this.scaleY = (double) canvasH / base.getHeight();
        }

        private double x(BigDecimal worldX) {
            return ((worldX.doubleValue() - originX) / resolution) * scaleX;
        }

        private double y(BigDecimal worldY) {
            return (imageHeight - (worldY.doubleValue() - originY) / resolution) * scaleY;
        }
    }

    private void drawZones(
            Graphics2D g,
            Projector projector,
            List<Checkpoint> zones,
            float labelSize,
            List<Rectangle2D> placed) {
        if (zones == null || zones.isEmpty()) return;

        Font font = font(labelSize);
        g.setFont(font);
        FontMetrics metrics = g.getFontMetrics();

        for (Checkpoint zone : zones) {
            double left = projector.x(zone.getMinX());
            double right = projector.x(zone.getMaxX());
            double top = projector.y(zone.getMaxY()); // maxY 가 화면 위쪽
            double bottom = projector.y(zone.getMinY());
            double w = Math.max(2, right - left);
            double h = Math.max(2, bottom - top);

            RoundRectangle2D box = new RoundRectangle2D.Double(left, top, w, h, 8 * SCALE, 8 * SCALE);
            g.setColor(ZONE_FILL);
            g.fill(box);
            g.setColor(ZONE_LINE);
            g.setStroke(
                    new BasicStroke(
                            1.6f * SCALE,
                            BasicStroke.CAP_ROUND,
                            BasicStroke.JOIN_ROUND,
                            10f,
                            new float[] {6f * SCALE, 4f * SCALE},
                            0f));
            g.draw(box);

            // 구역명 — 상자 안 왼쪽 위. 상자가 좁으면 글자가 넘치므로 상자 위로 올린다
            String name = zone.getName();
            int textW = metrics.stringWidth(name);
            float textX = (float) (left + 6 * SCALE);
            float textY = (float) (top + metrics.getAscent() + 5 * SCALE);
            if (textW + 12 * SCALE > w || metrics.getHeight() + 10 * SCALE > h) {
                textY = (float) (top - 4 * SCALE);
            }
            placed.add(labelBounds(metrics, textX, textY, textW));
            drawChip(g, metrics, name, textX, textY, LABEL_TEXT, null);
        }
    }

    private void drawRoute(
            Graphics2D g, Projector projector, List<PatrolRoutePointResponse> routePoints) {
        List<double[]> points = new ArrayList<>();
        if (routePoints != null) {
            for (PatrolRoutePointResponse point : routePoints) {
                if (point.getXCoordinate() == null || point.getYCoordinate() == null) continue;
                points.add(
                        new double[] {
                            projector.x(point.getXCoordinate()), projector.y(point.getYCoordinate())
                        });
            }
        }
        if (points.size() < 2) return;

        Path2D path = new Path2D.Double();
        path.moveTo(points.get(0)[0], points.get(0)[1]);
        for (int i = 1; i < points.size(); i++) {
            path.lineTo(points.get(i)[0], points.get(i)[1]);
        }

        g.setColor(ROUTE);
        g.setStroke(
                new BasicStroke(
                        2.6f * SCALE,
                        BasicStroke.CAP_ROUND,
                        BasicStroke.JOIN_ROUND,
                        10f,
                        new float[] {9f * SCALE, 7f * SCALE},
                        0f));
        g.draw(path);

        // 시작(채운 원) · 종료(비운 원)
        double[] start = points.get(0);
        double[] end = points.get(points.size() - 1);
        g.setStroke(new BasicStroke(2f * SCALE));
        double r = 5.0 * SCALE;
        g.setColor(ROUTE);
        g.fill(new Ellipse2D.Double(start[0] - r, start[1] - r, r * 2, r * 2));
        g.setColor(Color.WHITE);
        g.fill(new Ellipse2D.Double(end[0] - r, end[1] - r, r * 2, r * 2));
        g.setColor(ROUTE);
        g.draw(new Ellipse2D.Double(end[0] - r, end[1] - r, r * 2, r * 2));
    }

    private void drawEvents(
            Graphics2D g,
            Projector projector,
            List<PatrolTimelineResponse> timeline,
            Function<EventType, String> eventLabeler,
            float labelSize,
            List<Rectangle2D> placed) {
        if (timeline == null || timeline.isEmpty()) return;

        Font font = font(labelSize);
        g.setFont(font);
        FontMetrics metrics = g.getFontMetrics();

        for (PatrolTimelineResponse event : timeline) {
            if (event.getEventId() == null
                    || event.getXCoordinate() == null
                    || event.getYCoordinate() == null) {
                continue;
            }
            double px = projector.x(event.getXCoordinate());
            double py = projector.y(event.getYCoordinate());

            // 물방울 핀 — 팁이 발생 좌표에 꽂힌다 (화면과 같은 문법)
            double r = 5.5 * SCALE;
            double tail = 14.0 * SCALE;
            Path2D pin = new Path2D.Double();
            pin.moveTo(px, py);
            pin.lineTo(px - r * 0.75, py - tail + r * 0.5);
            pin.lineTo(px + r * 0.75, py - tail + r * 0.5);
            pin.closePath();
            g.setColor(EVENT);
            g.fill(pin);
            g.fill(new Ellipse2D.Double(px - r, py - tail - r, r * 2, r * 2));
            g.setColor(Color.WHITE);
            g.setStroke(new BasicStroke(1.4f * SCALE));
            g.draw(new Ellipse2D.Double(px - r, py - tail - r, r * 2, r * 2));
            double core = 1.9 * SCALE;
            g.fill(new Ellipse2D.Double(px - core, py - tail - core, core * 2, core * 2));

            // 이름표 — 핀 위가 기본, 이미 놓인 이름표와 겹치면 아래로 내린다
            String label = eventLabeler.apply(event.getEventType());
            int textW = metrics.stringWidth(label);
            float labelX = (float) (px - textW / 2.0);
            float top = (float) (py - tail - r * 2 - 4 * SCALE);
            float bottom = (float) (py + metrics.getAscent() + 6 * SCALE);
            float step = metrics.getHeight() + 4 * SCALE;
            float[] candidates = {
                top, bottom, top - step, bottom + step, top - step * 2, bottom + step * 2
            };
            float labelY = candidates[0];
            Rectangle2D candidate = labelBounds(metrics, labelX, labelY, textW);
            for (float option : candidates) {
                Rectangle2D box = labelBounds(metrics, labelX, option, textW);
                if (placed.stream().noneMatch(other -> other.intersects(box))) {
                    labelY = option;
                    candidate = box;
                    break;
                }
            }
            placed.add(candidate);
            drawChip(g, metrics, label, labelX, labelY, EVENT, CHIP_BG);
        }
    }

    private Rectangle2D labelBounds(FontMetrics metrics, float x, float y, int textW) {
        return new Rectangle2D.Double(
                x - 4 * SCALE,
                y - metrics.getAscent() - 3 * SCALE,
                textW + 8 * SCALE,
                metrics.getHeight() + 6 * SCALE);
    }

    /** 도면 위에서 글자가 묻히지 않도록 흰 칩을 깔고 글자를 얹는다 */
    private void drawChip(
            Graphics2D g,
            FontMetrics metrics,
            String text,
            float x,
            float y,
            Color textColor,
            Color background) {
        int textW = metrics.stringWidth(text);
        Color chip = background == null ? CHIP_BG : background;
        RoundRectangle2D box =
                new RoundRectangle2D.Double(
                        x - 4 * SCALE,
                        y - metrics.getAscent() - 2 * SCALE,
                        textW + 8 * SCALE,
                        metrics.getAscent() + 6 * SCALE,
                        6 * SCALE,
                        6 * SCALE);
        g.setColor(chip);
        g.fill(box);
        g.setColor(textColor);
        g.drawString(text, x, y);
    }

    private static synchronized Font font(float size) {
        if (baseFont == null) {
            try (InputStream stream = PatrolMapRenderer.class.getResourceAsStream(FONT_RESOURCE)) {
                baseFont =
                        stream == null
                                ? new Font(Font.SANS_SERIF, Font.BOLD, 12)
                                : Font.createFont(Font.TRUETYPE_FONT, stream);
            } catch (Exception exception) {
                baseFont = new Font(Font.SANS_SERIF, Font.BOLD, 12);
            }
        }
        return baseFont.deriveFont(Font.BOLD, size);
    }
}
