package com.oneloop.map.util;

import com.oneloop.map.domain.Checkpoint;
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

// 좌표(x, y)와 체크포인트 목록을 대조하는 공용 로직.
@Component
public class CheckpointLocator {

    private static final String NEARBY_SUFFIX = " 근처";

    // 좌표가 속한 체크포인트 이름을 찾는다. 정확히 속하는 구역이 없으면 가장 가까운 체크포인트 이름에 "근처"를 붙여 반환한다.
    // 좌표가 없거나 체크포인트가 하나도 없으면 null
    public String resolveLocationName(List<Checkpoint> checkpoints, BigDecimal x, BigDecimal y) {
        if (x == null || y == null || checkpoints.isEmpty()) {
            return null;
        }
        return findContaining(checkpoints, x, y)
                .map(Checkpoint::getName)
                .orElseGet(
                        () ->
                                findNearest(checkpoints, x, y)
                                        .map(checkpoint -> checkpoint.getName() + NEARBY_SUFFIX)
                                        .orElse(null));
    }

    // 좌표(x, y)가 체크포인트의 사각 영역(minX~maxX, minY~maxY) 안에 정확히 속하는 체크포인트를 찾는다
    public Optional<Checkpoint> findContaining(List<Checkpoint> checkpoints, BigDecimal x, BigDecimal y) {
        if (x == null || y == null) {
            return Optional.empty();
        }
        return checkpoints.stream().filter(checkpoint -> contains(checkpoint, x, y)).findFirst();
    }

    private boolean contains(Checkpoint checkpoint, BigDecimal x, BigDecimal y) {
        return x.compareTo(checkpoint.getMinX()) >= 0
                && x.compareTo(checkpoint.getMaxX()) <= 0
                && y.compareTo(checkpoint.getMinY()) >= 0
                && y.compareTo(checkpoint.getMaxY()) <= 0;
    }

    // 어느 구역에도 속하지 않을 때, 체크포인트 중심점과의 거리가 가장 가까운 체크포인트를 찾는다
    private Optional<Checkpoint> findNearest(List<Checkpoint> checkpoints, BigDecimal x, BigDecimal y) {
        return checkpoints.stream()
                .min(Comparator.comparingDouble(checkpoint -> distanceToCenter(checkpoint, x, y)));
    }

    private double distanceToCenter(Checkpoint checkpoint, BigDecimal x, BigDecimal y) {
        double centerX = (checkpoint.getMinX().doubleValue() + checkpoint.getMaxX().doubleValue()) / 2;
        double centerY = (checkpoint.getMinY().doubleValue() + checkpoint.getMaxY().doubleValue()) / 2;
        double dx = x.doubleValue() - centerX;
        double dy = y.doubleValue() - centerY;
        return Math.sqrt(dx * dx + dy * dy);
    }
}
