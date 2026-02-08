ALTER TABLE universal_notification_queue
ADD COLUMN IF NOT EXISTS user_email VARCHAR(320);

CREATE INDEX IF NOT EXISTS idx_universal_notification_user_email
ON universal_notification_queue(user_email)
WHERE user_email IS NOT NULL;
