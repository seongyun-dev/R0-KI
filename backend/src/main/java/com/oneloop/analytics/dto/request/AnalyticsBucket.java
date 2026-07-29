package com.oneloop.analytics.dto.request;

/**
 * 추이 집계 단위.
 * 프론트가 차트 X축을 어떤 간격으로 그릴지 정할 때 사용한다.
 *
 * <ul>
 *   <li>day / week / month: 달력 기준 시계열 (빈 구간도 series에 포함)
 *   <li>hour3: 하루를 3시간 슬롯 8칸(0-3 … 21-24)으로 나눈 뒤,
 *       조회 기간 전체 이벤트를 "시각대" 기준으로 합산 (날짜는 무시하고 시각만 본다).
 *       프론트 시간대별 유형 차트용.
 * </ul>
 */
public enum AnalyticsBucket {
    day,
    week,
    month,
    /** 3시간 단위 시각대 집계 (기간 내 동일 시각대 합산) */
    hour3
}
