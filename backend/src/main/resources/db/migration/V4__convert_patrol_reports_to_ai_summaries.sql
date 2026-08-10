ALTER TABLE patrol_reports
    ADD COLUMN generation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING';
ALTER TABLE patrol_reports
    ADD COLUMN summary_content TEXT;

UPDATE patrol_reports
SET summary_content = patrol_summary,
    generation_status = CASE
        WHEN patrol_summary IS NULL THEN 'PENDING'
        ELSE 'COMPLETED'
    END;

ALTER TABLE patrol_reports
    DROP COLUMN report_title;
ALTER TABLE patrol_reports
    DROP COLUMN report_content;
ALTER TABLE patrol_reports
    DROP COLUMN total_event_count;
ALTER TABLE patrol_reports
    DROP COLUMN emergency_event_count;
ALTER TABLE patrol_reports
    DROP COLUMN patrol_summary;

ALTER TABLE patrol_reports
    RENAME TO patrol_ai_summaries;
ALTER TABLE patrol_ai_summaries
    RENAME COLUMN report_id TO ai_summary_id;

ALTER TABLE patrols
    ADD COLUMN start_battery_level DECIMAL(5, 2);
ALTER TABLE patrols
    ADD COLUMN end_battery_level DECIMAL(5, 2);
