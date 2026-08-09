package com.oneloop.analytics.service;

import com.oneloop.analytics.domain.AnalyticsInsightPeriodType;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import java.time.DayOfWeek;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import lombok.Getter;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/**
 * AI 인사이트 분석 구간 계산기.
 *
 * <p>기본({@link #resolve(AnalyticsInsightPeriodType)})은 직전 완료 주/월.
 * {@code periodKey}가 있으면 해당 키의 구간을 해석한다 (예: {@code 2026-W30}, {@code 2026-07}).
 * 타임존은 통계 API와 동일하게 Asia/Seoul.
 */
@Component
public class AnalyticsInsightPeriodResolver {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final WeekFields ISO_WEEK = WeekFields.ISO;
    private static final DateTimeFormatter MONTH_KEY = DateTimeFormatter.ofPattern("yyyy-MM");
    private static final Pattern WEEK_KEY = Pattern.compile("^(\\d{4})-W(\\d{2})$");

    /** periodKey 미지정 — 직전 완료 주/월. */
    public ResolvedPeriod resolve(AnalyticsInsightPeriodType periodType) {
        LocalDate today = LocalDate.now(SERVICE_ZONE);
        return switch (periodType) {
            case WEEK -> resolvePreviousWeek(today);
            case MONTH -> resolvePreviousMonth(today);
        };
    }

    /**
     * periodKey 지정 조회.
     *
     * <p>포맷이 틀리거나, 아직 끝나지 않은(진행 중)·미래 구간이면 {@link ErrorCode#INVALID_INPUT}.
     */
    public ResolvedPeriod resolve(AnalyticsInsightPeriodType periodType, String periodKey) {
        if (!StringUtils.hasText(periodKey)) {
            return resolve(periodType);
        }

        String normalized = periodKey.trim();
        ResolvedPeriod period =
                switch (periodType) {
                    case WEEK -> resolveWeekKey(normalized);
                    case MONTH -> resolveMonthKey(normalized);
                };

        if (!isComplete(period)) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }
        return period;
    }

    private ResolvedPeriod resolvePreviousWeek(LocalDate today) {
        LocalDate thisWeekMonday = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        LocalDate previousWeekMonday = thisWeekMonday.minusWeeks(1);
        return ofWeek(previousWeekMonday);
    }

    private ResolvedPeriod resolvePreviousMonth(LocalDate today) {
        LocalDate firstDayOfPreviousMonth = today.withDayOfMonth(1).minusMonths(1);
        return ofMonth(firstDayOfPreviousMonth);
    }

    private ResolvedPeriod resolveWeekKey(String periodKey) {
        Matcher matcher = WEEK_KEY.matcher(periodKey);
        if (!matcher.matches()) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }

        int weekBasedYear = Integer.parseInt(matcher.group(1));
        int weekOfYear = Integer.parseInt(matcher.group(2));
        if (weekOfYear < 1 || weekOfYear > 53) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }

        LocalDate monday;
        try {
            monday =
                    LocalDate.of(weekBasedYear, 1, 4)
                            .with(ISO_WEEK.weekOfWeekBasedYear(), weekOfYear)
                            .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        } catch (DateTimeException exception) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }

        // 파싱 결과가 요청 키와 다르면(예: 존재하지 않는 W53) 거절
        String canonical = weekKeyOf(monday);
        if (!canonical.equals(periodKey)) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }
        return ofWeek(monday);
    }

    private ResolvedPeriod resolveMonthKey(String periodKey) {
        final LocalDate firstDay;
        try {
            firstDay = LocalDate.parse(periodKey + "-01");
        } catch (DateTimeParseException exception) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }
        if (!firstDay.format(MONTH_KEY).equals(periodKey)) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }
        return ofMonth(firstDay);
    }

    private ResolvedPeriod ofWeek(LocalDate monday) {
        LocalDate sunday = monday.plusDays(6);
        return new ResolvedPeriod(
                AnalyticsInsightPeriodType.WEEK,
                weekKeyOf(monday),
                monday.atStartOfDay(),
                LocalDateTime.of(sunday, LocalTime.MAX),
                SERVICE_ZONE.getId());
    }

    private ResolvedPeriod ofMonth(LocalDate firstDay) {
        LocalDate lastDay = firstDay.with(TemporalAdjusters.lastDayOfMonth());
        return new ResolvedPeriod(
                AnalyticsInsightPeriodType.MONTH,
                firstDay.format(MONTH_KEY),
                firstDay.atStartOfDay(),
                LocalDateTime.of(lastDay, LocalTime.MAX),
                SERVICE_ZONE.getId());
    }

    private String weekKeyOf(LocalDate monday) {
        int weekBasedYear = monday.get(ISO_WEEK.weekBasedYear());
        int weekOfYear = monday.get(ISO_WEEK.weekOfWeekBasedYear());
        return String.format("%d-W%02d", weekBasedYear, weekOfYear);
    }

    /** 구간 종료일이 오늘(KST)보다 이전이면 완료된 기간. */
    public boolean isComplete(ResolvedPeriod period) {
        LocalDate today = LocalDate.now(SERVICE_ZONE);
        return period.getPeriodTo().toLocalDate().isBefore(today);
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
