package com.oneloop.analytics.dto.request;

/**
 * 구역별 통계 정렬 옵션.
 * - count_desc: 이벤트 많은 구역 우선 (기본)
 * - rate_desc: 순찰 대비 발생 비율 높은 구역 우선
 */
public enum ZoneSort {
    count_desc,
    rate_desc
}
