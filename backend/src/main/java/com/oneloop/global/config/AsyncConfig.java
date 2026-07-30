package com.oneloop.global.config;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean(name = "patrolSummaryExecutor")
    public Executor patrolSummaryExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        /*
         * @Async는 메서드를 별도 스레드에서 실행하게 하지만, 실행할 스레드의 수와 대기열 크기까지
         * 결정하지는 않는다. GMS 응답을 기다리는 요약 작업이 일반 요청 처리에 영향을 주지 않도록
         * AI 요약 전용 스레드 풀을 사용한다.
         */
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("patrol-summary-");

        /*
         * 서버가 정상 종료될 때 이미 실행 중인 요약 작업을 바로 끊지 않고 최대 30초 동안 기다린다.
         * 대기열은 메모리에 있으므로 비정상 종료까지 보장하지는 않으며, DB의 PENDING/PROCESSING
         * 상태를 이용한 재처리 기능은 별도로 확장할 수 있다.
         */
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }

    // SMS 발송(solapi 호출)이 일반 요청 처리에 영향을 주지 않도록 전용 스레드 풀을 쓴다.
    @Bean(name = "notificationExecutor")
    public Executor notificationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("notification-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }
}
