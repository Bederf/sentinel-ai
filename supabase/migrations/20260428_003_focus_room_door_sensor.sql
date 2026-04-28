-- Focus Room Door Sensor — Phase TBD
-- Adds door_closed state to focus room sessions so the door signal
-- survives across events and the gap-freeze logic is correct.
--
-- door_closed: true  = door shut behind person, gap frozen, 2hr timer running
-- door_closed: false = door open, normal presence + gap tolerance applies
-- door_closed: NULL  = no door sensor installed, fall back to radar-only logic

ALTER TABLE space_focus_room_sessions
ADD COLUMN door_closed BOOLEAN NULL;

COMMENT ON COLUMN space_focus_room_sessions.door_closed IS
  'Door closed signal from magnetic reed switch. True=closed (person checked out). NULL=no sensor.';
