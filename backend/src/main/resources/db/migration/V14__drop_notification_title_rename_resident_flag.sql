ALTER TABLE notifications DROP COLUMN notification_title;

ALTER TABLE residents RENAME COLUMN kakao_notification_enabled TO notification_enabled;
