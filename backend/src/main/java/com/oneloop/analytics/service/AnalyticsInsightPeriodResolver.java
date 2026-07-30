package com.oneloop.analytics.service;

import com.oneloop.analytics.domain.AnalyticsInsightPeriodType;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import lombok.Getter;
import org.springframework.stereotype.Component;

/**
 * AI 인사이트 분석 구간(직전 완료 주/월) 계산기.
 *
 * <p>화면이 "이번 주/이번 달"이어도 인사이트는 지난 완료 구간 기준이다.
 * 타임존은 통계 API와 동일하게 Asia/Seoul.
 */
@Component
public class AnalyticsInsightPeriodResolver {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final WeekFields ISO_WEEK = WeekFields.ISO;
    private static final DateTimeFormatter MONTH_KEY = DateTimeFormatter.ofPattern("yyyy-MM");

    public ResolvedPeriod resolve(AnalyticsInsightPeriodType periodType) {
        LocalDate today = LocalDate.now(SERVICE_ZONE);
        return switch (periodType) {
            case WEEK -> resolvePreviousWeek(today);
            case MONTH -> resolvePreviousMonth(today);
        };
    }

    private ResolvedPeriod resolvePreviousWeek(LocalDate today) {
        LocalDate thisWeekMonday = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        LocalDate previousWeekMonday = thisWeekMonday.minusWeeks(1);
        LocalDate previousWeekSunday = previousWeekMonday.plusDays(6);

        int weekBasedYear = previousWeekMonday.get(ISO_WEEK.weekBasedYear());
        int weekOfYear = previousWeekMonday.get(ISO_WEEK.weekOfWeekBasedYear());
        String periodKey = String.format("%d-W%02d", weekBasedYear, weekOfYear);

        return new ResolvedPeriod(
                AnalyticsInsightPeriodType.WEEK,
                periodKey,
                previousWeekMonday.atStartOfDay(),
                LocalDateTime.of(previousWeekSunday, LocalTime.MAX),
                SERVICE_ZONE.getId());
    }

    private ResolvedPeriod resolvePreviousMonth(LocalDate today) {
        LocalDate firstDayOfPreviousMonth =
                today.withDayOfMonth(1).minusMonths(1);
        LocalDate lastDayOfPreviousMonth =
                firstDayOfPreviousMonth.with(TemporalAdjusters.lastDayOfMonth());

        return new ResolvedPeriod(
                AnalyticsInsightPeriodType.MONTH,
                firstDayOfPreviousMonth.format(MONTH_KEY),
                firstDayOfPreviousMonth.atStartOfDay(),
                LocalDateTime.of(lastDayOfPreviousMonth, LocalTime.MAX),
                SERVICE_ZONE.getId());
    }

    @Getter
    public static class ResolvedPeriod {
        private final AnalyticsInsightPeriodType periodType;
        private final String periodKey;
        private final LocalDateTime periodFrom;
        private final LocalDateTime periodTo;
        private final String timezone;

        public ResolvedPeriod(
                AnalyticsInsightPeriodType periodType,
                String periodKey,
                LocalDateTime periodFrom,
                LocalDateTime periodTo,
                String timezone) {
            this.periodType = periodType;
            this.periodKey = periodKey;
            this.periodFrom = periodFrom;
            this.periodTo = periodTo;
            this.timezone = timezone;
        }
    }
}
