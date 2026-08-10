CREATE TABLE analytics_ai_insights (
    insight_id BIGINT NOT NULL AUTO_INCREMENT,
    apartment_complex_id BIGINT NOT NULL,
    period_type VARCHAR(10) NOT NULL,
    period_key VARCHAR(16) NOT NULL,
    period_from DATETIME(6) NOT NULL,
    period_to DATETIME(6) NOT NULL,
    generation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    insight_content MEDIUMTEXT,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_analytics_ai_insights PRIMARY KEY (insight_id),
    CONSTRAINT uk_analytics_ai_insights_apartment_period
        UNIQUE (apartment_complex_id, period_type, period_key),
    CONSTRAINT fk_analytics_ai_insights_apartment_complex
        FOREIGN KEY (apartment_complex_id)
        REFERENCES apartment_complexes (apartment_complex_id)
);

CREATE INDEX idx_analytics_ai_insights_apartment_complex_id
    ON analytics_ai_insights (apartment_complex_id);
