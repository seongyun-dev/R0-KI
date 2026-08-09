package com.oneloop.global.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Spring 스케줄러 활성화.
 *
 * <p>AsyncConfig 와 분리한 이유: 비동기 풀 설정과 cron 스케줄 책임이 다르다.
 */
@Configuration
@EnableScheduling
public class SchedulingConfig {}
