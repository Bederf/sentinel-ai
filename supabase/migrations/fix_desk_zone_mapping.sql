-- Fix desk-to-zone mappings for S002 (Sandton)
-- desk_id is stored as 3-digit text for L2 (e.g., '240' for desk 240)
-- desk_id numeric value determines zone:
-- L0: desk 0-99 (single or 2 digits) -> Zone-001 to Zone-005
-- L1: desk 100-199 (3 digits) -> extract last 2 digits -> Zone-101 to Zone-105
-- L2: desk 200-299 (3 digits) -> extract last 2 digits -> Zone-201 to Zone-205
-- L3: desk 300-399 (3 digits) -> extract last 2 digits -> Zone-301 to Zone-305

-- Step 1: Update Ground floor desks (L0) - desk_id as integer 0-99
UPDATE desks
SET zone_id = CASE
    WHEN CAST(desk_id AS INTEGER) BETWEEN 0 AND 19 THEN 'Zone-001'
    WHEN CAST(desk_id AS INTEGER) BETWEEN 20 AND 39 THEN 'Zone-002'
    WHEN CAST(desk_id AS INTEGER) BETWEEN 40 AND 59 THEN 'Zone-003'
    WHEN CAST(desk_id AS INTEGER) BETWEEN 60 AND 79 THEN 'Zone-004'
    WHEN CAST(desk_id AS INTEGER) BETWEEN 80 AND 99 THEN 'Zone-005'
    ELSE zone_id
  END
WHERE floor = 'L0'
  AND site_id = (SELECT id FROM sites WHERE code = 'site-002');

-- Step 2: Update Level 1 desks (L1) - desk_id as '1NN'
UPDATE desks
SET zone_id = CASE
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 0 AND 19 THEN 'Zone-101'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 20 AND 39 THEN 'Zone-102'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 40 AND 59 THEN 'Zone-103'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 60 AND 79 THEN 'Zone-104'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 80 AND 99 THEN 'Zone-105'
    ELSE zone_id
  END
WHERE floor = 'L1'
  AND site_id = (SELECT id FROM sites WHERE code = 'site-002');

-- Step 3: Update Level 2 desks (L2) - desk_id as '2NN'
-- Desk 240 stored as '240' -> SUBSTRING('240' FROM 2) = '40' -> numeric 40 -> Zone-203
-- Desk 211 stored as '211' -> SUBSTRING('211' FROM 2) = '11' -> numeric 11 -> Zone-201
UPDATE desks
SET zone_id = CASE
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 0 AND 19 THEN 'Zone-201'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 20 AND 39 THEN 'Zone-202'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 40 AND 59 THEN 'Zone-203'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 60 AND 79 THEN 'Zone-204'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 80 AND 99 THEN 'Zone-205'
    ELSE zone_id
  END
WHERE floor = 'L2'
  AND site_id = (SELECT id FROM sites WHERE code = 'site-002');

-- Step 4: Update Level 3 desks (L3) - desk_id as '3NN'
UPDATE desks
SET zone_id = CASE
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 0 AND 19 THEN 'Zone-301'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 20 AND 39 THEN 'Zone-302'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 40 AND 59 THEN 'Zone-303'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 60 AND 79 THEN 'Zone-304'
    WHEN CAST(SUBSTRING(desk_id FROM 2) AS INTEGER) BETWEEN 80 AND 99 THEN 'Zone-305'
    ELSE zone_id
  END
WHERE floor = 'L3'
  AND site_id = (SELECT id FROM sites WHERE code = 'site-002');