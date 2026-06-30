ALTER TABLE meeting_rooms ADD COLUMN IF NOT EXISTS keywords TEXT[] DEFAULT '{}';

COMMENT ON COLUMN meeting_rooms.keywords IS 'Custom keywords for email routing — when rooms@ mailbox receives an email whose subject matches a room keyword, it is routed as a signal to that room.';
