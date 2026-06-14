-- Phase 227 rollback
DROP INDEX IF EXISTS idx_bot_users_site_role;
DROP INDEX IF EXISTS idx_bot_users_lookup;
DROP TABLE IF EXISTS bot_users;
