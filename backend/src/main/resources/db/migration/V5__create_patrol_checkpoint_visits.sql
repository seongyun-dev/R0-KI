CREATE TABLE patrol_checkpoint_visits (
    visit_id BIGINT NOT NULL AUTO_INCREMENT,
    patrol_id BIGINT NOT NULL,
    checkpoint_id BIGINT NOT NULL,
    visit_sequence INT NOT NULL,
    visited_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT pk_patrol_checkpoint_visits PRIMARY KEY (visit_id),
    CONSTRAINT uk_patrol_checkpoint_visits_patrol_sequence
        UNIQUE (patrol_id, visit_sequence),
    CONSTRAINT fk_patrol_checkpoint_visits_patrol
        FOREIGN KEY (patrol_id)
        REFERENCES patrols (patrol_id),
    CONSTRAINT fk_patrol_checkpoint_visits_checkpoint
        FOREIGN KEY (checkpoint_id)
        REFERENCES checkpoints (checkpoint_id)
);

CREATE INDEX idx_patrol_checkpoint_visits_checkpoint_id
    ON patrol_checkpoint_visits (checkpoint_id);
