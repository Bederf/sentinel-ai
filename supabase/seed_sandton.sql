-- =====================================================
-- Seed: Sandton City Office Tower (site-002)
-- Building UUID: 50a24fb7-80f3-5e0b-9aa3-bf0939b923d9
-- Data: 15 HVAC zones, 300 desks, 57 DALI controllers,
--       10 DALI zones, 46 sensors, 32 luminaires
-- =====================================================

-- Building reference
DO $$
DECLARE
  sandton_id UUID := '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9';
BEGIN
  -- Verify building exists
  IF NOT EXISTS (SELECT 1 FROM buildings WHERE id = sandton_id) THEN
    RAISE EXCEPTION 'Sandton building not found. Run initial seed first.';
  END IF;
END $$;

-- =====================================================
-- HVAC ZONES (15 zones: 5 per floor L10-L12)
-- =====================================================
INSERT INTO hvac_zones (zone_id, zone_name, building_id, floor, fcu_id, vav_id, ahu_id, temp_sensor, co2_sensor, typical_occupancy, area_sqm, setpoint, current_temp, status)
VALUES
  -- Level 12 (5 zones)
  ('Zone-L12-A', 'Level 12 Zone A', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L12', 'FCU-L12-01', 'VAV-L12-01', 'AHU-L12-01', 'TS-L12-01', 'CO2-L12-01', 20, 200, 21.0, 20.7, 'running'),
  ('Zone-L12-B', 'Level 12 Zone B', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L12', 'FCU-L12-02', 'VAV-L12-02', 'AHU-L12-01', 'TS-L12-02', 'CO2-L12-02', 20, 200, 21.0, 21.4, 'running'),
  ('Zone-L12-C', 'Level 12 Zone C', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L12', 'FCU-L12-03', 'VAV-L12-03', 'AHU-L12-01', 'TS-L12-03', 'CO2-L12-03', 20, 200, 21.0, 21.4, 'running'),
  ('Zone-L12-D', 'Level 12 Zone D', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L12', 'FCU-L12-04', 'VAV-L12-04', 'AHU-L12-01', 'TS-L12-04', 'CO2-L12-04', 20, 200, 21.0, 21.4, 'running'),
  ('Zone-L12-E', 'Level 12 Zone E', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L12', 'FCU-L12-05', 'VAV-L12-05', 'AHU-L12-01', 'TS-L12-05', 'CO2-L12-05', 20, 200, 21.0, 21.3, 'running'),
  -- Level 11 (5 zones)
  ('Zone-L11-A', 'Level 11 Zone A', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L11', 'FCU-L11-01', 'VAV-L11-01', 'AHU-L11-01', 'TS-L11-01', 'CO2-L11-01', 20, 200, 21.0, 20.9, 'running'),
  ('Zone-L11-B', 'Level 11 Zone B', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L11', 'FCU-L11-02', 'VAV-L11-02', 'AHU-L11-01', 'TS-L11-02', 'CO2-L11-02', 20, 200, 21.0, 21.1, 'running'),
  ('Zone-L11-C', 'Level 11 Zone C', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L11', 'FCU-L11-03', 'VAV-L11-03', 'AHU-L11-01', 'TS-L11-03', 'CO2-L11-03', 20, 200, 21.0, 21.5, 'running'),
  ('Zone-L11-D', 'Level 11 Zone D', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L11', 'FCU-L11-04', 'VAV-L11-04', 'AHU-L11-01', 'TS-L11-04', 'CO2-L11-04', 20, 200, 21.0, 20.7, 'running'),
  ('Zone-L11-E', 'Level 11 Zone E', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L11', 'FCU-L11-05', 'VAV-L11-05', 'AHU-L11-01', 'TS-L11-05', 'CO2-L11-05', 20, 200, 21.0, 21.1, 'running'),
  -- Level 10 (5 zones)
  ('Zone-L10-A', 'Level 10 Zone A', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L10', 'FCU-L10-01', 'VAV-L10-01', 'AHU-L10-01', 'TS-L10-01', 'CO2-L10-01', 20, 200, 21.0, 21.3, 'running'),
  ('Zone-L10-B', 'Level 10 Zone B', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L10', 'FCU-L10-02', 'VAV-L10-02', 'AHU-L10-01', 'TS-L10-02', 'CO2-L10-02', 20, 200, 21.0, 20.7, 'running'),
  ('Zone-L10-C', 'Level 10 Zone C', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L10', 'FCU-L10-03', 'VAV-L10-03', 'AHU-L10-01', 'TS-L10-03', 'CO2-L10-03', 20, 200, 21.0, 25.0, 'fault'),
  ('Zone-L10-D', 'Level 10 Zone D', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L10', 'FCU-L10-04', 'VAV-L10-04', 'AHU-L10-01', 'TS-L10-04', 'CO2-L10-04', 20, 200, 21.0, 21.4, 'running'),
  ('Zone-L10-E', 'Level 10 Zone E', '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9', 'L10', 'FCU-L10-05', 'VAV-L10-05', 'AHU-L10-01', 'TS-L10-05', 'CO2-L10-05', 20, 200, 21.0, 21.0, 'running')
ON CONFLICT (zone_id) DO UPDATE SET
  current_temp = EXCLUDED.current_temp,
  status = EXCLUDED.status,
  updated_at = NOW();

-- =====================================================
-- DESKS (300 desks: 20 per zone, 100 per floor)
-- Using context cycling: near_diffuser, near_printer, open_plan, corner, near_window
-- =====================================================

-- Helper function to map context string to boolean columns
-- Contexts: near_diffuser, near_printer, open_plan, corner, near_window

-- Level 10 desks (1001-1100)
INSERT INTO desks (desk_id, building_id, floor, hvac_zone_id, near_diffuser, near_printer, near_window)
SELECT
  d.desk_id,
  '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9'::UUID,
  'L10',
  hz.id,
  d.context = 'near_diffuser',
  d.context = 'near_printer',
  d.context = 'near_window'
FROM (
  VALUES
    -- Zone A (1001-1020)
    ('1001', 'Zone-L10-A', 'near_diffuser'), ('1002', 'Zone-L10-A', 'near_printer'), ('1003', 'Zone-L10-A', 'open_plan'), ('1004', 'Zone-L10-A', 'corner'), ('1005', 'Zone-L10-A', 'near_window'),
    ('1006', 'Zone-L10-A', 'near_diffuser'), ('1007', 'Zone-L10-A', 'near_printer'), ('1008', 'Zone-L10-A', 'open_plan'), ('1009', 'Zone-L10-A', 'corner'), ('1010', 'Zone-L10-A', 'near_window'),
    ('1011', 'Zone-L10-A', 'near_diffuser'), ('1012', 'Zone-L10-A', 'near_printer'), ('1013', 'Zone-L10-A', 'open_plan'), ('1014', 'Zone-L10-A', 'corner'), ('1015', 'Zone-L10-A', 'near_window'),
    ('1016', 'Zone-L10-A', 'near_diffuser'), ('1017', 'Zone-L10-A', 'near_printer'), ('1018', 'Zone-L10-A', 'open_plan'), ('1019', 'Zone-L10-A', 'corner'), ('1020', 'Zone-L10-A', 'near_window'),
    -- Zone B (1021-1040)
    ('1021', 'Zone-L10-B', 'near_window'), ('1022', 'Zone-L10-B', 'near_diffuser'), ('1023', 'Zone-L10-B', 'near_printer'), ('1024', 'Zone-L10-B', 'open_plan'), ('1025', 'Zone-L10-B', 'corner'),
    ('1026', 'Zone-L10-B', 'near_window'), ('1027', 'Zone-L10-B', 'near_diffuser'), ('1028', 'Zone-L10-B', 'near_printer'), ('1029', 'Zone-L10-B', 'open_plan'), ('1030', 'Zone-L10-B', 'corner'),
    ('1031', 'Zone-L10-B', 'near_window'), ('1032', 'Zone-L10-B', 'near_diffuser'), ('1033', 'Zone-L10-B', 'near_printer'), ('1034', 'Zone-L10-B', 'open_plan'), ('1035', 'Zone-L10-B', 'corner'),
    ('1036', 'Zone-L10-B', 'near_window'), ('1037', 'Zone-L10-B', 'near_diffuser'), ('1038', 'Zone-L10-B', 'near_printer'), ('1039', 'Zone-L10-B', 'open_plan'), ('1040', 'Zone-L10-B', 'corner'),
    -- Zone C (1041-1060)
    ('1041', 'Zone-L10-C', 'corner'), ('1042', 'Zone-L10-C', 'near_window'), ('1043', 'Zone-L10-C', 'near_diffuser'), ('1044', 'Zone-L10-C', 'near_printer'), ('1045', 'Zone-L10-C', 'open_plan'),
    ('1046', 'Zone-L10-C', 'corner'), ('1047', 'Zone-L10-C', 'near_window'), ('1048', 'Zone-L10-C', 'near_diffuser'), ('1049', 'Zone-L10-C', 'near_printer'), ('1050', 'Zone-L10-C', 'open_plan'),
    ('1051', 'Zone-L10-C', 'corner'), ('1052', 'Zone-L10-C', 'near_window'), ('1053', 'Zone-L10-C', 'near_diffuser'), ('1054', 'Zone-L10-C', 'near_printer'), ('1055', 'Zone-L10-C', 'open_plan'),
    ('1056', 'Zone-L10-C', 'corner'), ('1057', 'Zone-L10-C', 'near_window'), ('1058', 'Zone-L10-C', 'near_diffuser'), ('1059', 'Zone-L10-C', 'near_printer'), ('1060', 'Zone-L10-C', 'open_plan'),
    -- Zone D (1061-1080)
    ('1061', 'Zone-L10-D', 'open_plan'), ('1062', 'Zone-L10-D', 'corner'), ('1063', 'Zone-L10-D', 'near_window'), ('1064', 'Zone-L10-D', 'near_diffuser'), ('1065', 'Zone-L10-D', 'near_printer'),
    ('1066', 'Zone-L10-D', 'open_plan'), ('1067', 'Zone-L10-D', 'corner'), ('1068', 'Zone-L10-D', 'near_window'), ('1069', 'Zone-L10-D', 'near_diffuser'), ('1070', 'Zone-L10-D', 'near_printer'),
    ('1071', 'Zone-L10-D', 'open_plan'), ('1072', 'Zone-L10-D', 'corner'), ('1073', 'Zone-L10-D', 'near_window'), ('1074', 'Zone-L10-D', 'near_diffuser'), ('1075', 'Zone-L10-D', 'near_printer'),
    ('1076', 'Zone-L10-D', 'open_plan'), ('1077', 'Zone-L10-D', 'corner'), ('1078', 'Zone-L10-D', 'near_window'), ('1079', 'Zone-L10-D', 'near_diffuser'), ('1080', 'Zone-L10-D', 'near_printer'),
    -- Zone E (1081-1100)
    ('1081', 'Zone-L10-E', 'near_printer'), ('1082', 'Zone-L10-E', 'open_plan'), ('1083', 'Zone-L10-E', 'corner'), ('1084', 'Zone-L10-E', 'near_window'), ('1085', 'Zone-L10-E', 'near_diffuser'),
    ('1086', 'Zone-L10-E', 'near_printer'), ('1087', 'Zone-L10-E', 'open_plan'), ('1088', 'Zone-L10-E', 'corner'), ('1089', 'Zone-L10-E', 'near_window'), ('1090', 'Zone-L10-E', 'near_diffuser'),
    ('1091', 'Zone-L10-E', 'near_printer'), ('1092', 'Zone-L10-E', 'open_plan'), ('1093', 'Zone-L10-E', 'corner'), ('1094', 'Zone-L10-E', 'near_window'), ('1095', 'Zone-L10-E', 'near_diffuser'),
    ('1096', 'Zone-L10-E', 'near_printer'), ('1097', 'Zone-L10-E', 'open_plan'), ('1098', 'Zone-L10-E', 'corner'), ('1099', 'Zone-L10-E', 'near_window'), ('1100', 'Zone-L10-E', 'near_diffuser')
) AS d(desk_id, zone_id, context)
JOIN hvac_zones hz ON hz.zone_id = d.zone_id
ON CONFLICT (desk_id) DO UPDATE SET
  hvac_zone_id = EXCLUDED.hvac_zone_id,
  updated_at = NOW();

-- Level 11 desks (1101-1200)
INSERT INTO desks (desk_id, building_id, floor, hvac_zone_id, near_diffuser, near_printer, near_window)
SELECT
  d.desk_id,
  '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9'::UUID,
  'L11',
  hz.id,
  d.context = 'near_diffuser',
  d.context = 'near_printer',
  d.context = 'near_window'
FROM (
  VALUES
    -- Zone A (1101-1120)
    ('1101', 'Zone-L11-A', 'near_diffuser'), ('1102', 'Zone-L11-A', 'near_printer'), ('1103', 'Zone-L11-A', 'open_plan'), ('1104', 'Zone-L11-A', 'corner'), ('1105', 'Zone-L11-A', 'near_window'),
    ('1106', 'Zone-L11-A', 'near_diffuser'), ('1107', 'Zone-L11-A', 'near_printer'), ('1108', 'Zone-L11-A', 'open_plan'), ('1109', 'Zone-L11-A', 'corner'), ('1110', 'Zone-L11-A', 'near_window'),
    ('1111', 'Zone-L11-A', 'near_diffuser'), ('1112', 'Zone-L11-A', 'near_printer'), ('1113', 'Zone-L11-A', 'open_plan'), ('1114', 'Zone-L11-A', 'corner'), ('1115', 'Zone-L11-A', 'near_window'),
    ('1116', 'Zone-L11-A', 'near_diffuser'), ('1117', 'Zone-L11-A', 'near_printer'), ('1118', 'Zone-L11-A', 'open_plan'), ('1119', 'Zone-L11-A', 'corner'), ('1120', 'Zone-L11-A', 'near_window'),
    -- Zone B (1121-1140)
    ('1121', 'Zone-L11-B', 'near_window'), ('1122', 'Zone-L11-B', 'near_diffuser'), ('1123', 'Zone-L11-B', 'near_printer'), ('1124', 'Zone-L11-B', 'open_plan'), ('1125', 'Zone-L11-B', 'corner'),
    ('1126', 'Zone-L11-B', 'near_window'), ('1127', 'Zone-L11-B', 'near_diffuser'), ('1128', 'Zone-L11-B', 'near_printer'), ('1129', 'Zone-L11-B', 'open_plan'), ('1130', 'Zone-L11-B', 'corner'),
    ('1131', 'Zone-L11-B', 'near_window'), ('1132', 'Zone-L11-B', 'near_diffuser'), ('1133', 'Zone-L11-B', 'near_printer'), ('1134', 'Zone-L11-B', 'open_plan'), ('1135', 'Zone-L11-B', 'corner'),
    ('1136', 'Zone-L11-B', 'near_window'), ('1137', 'Zone-L11-B', 'near_diffuser'), ('1138', 'Zone-L11-B', 'near_printer'), ('1139', 'Zone-L11-B', 'open_plan'), ('1140', 'Zone-L11-B', 'corner'),
    -- Zone C (1141-1160)
    ('1141', 'Zone-L11-C', 'corner'), ('1142', 'Zone-L11-C', 'near_window'), ('1143', 'Zone-L11-C', 'near_diffuser'), ('1144', 'Zone-L11-C', 'near_printer'), ('1145', 'Zone-L11-C', 'open_plan'),
    ('1146', 'Zone-L11-C', 'corner'), ('1147', 'Zone-L11-C', 'near_window'), ('1148', 'Zone-L11-C', 'near_diffuser'), ('1149', 'Zone-L11-C', 'near_printer'), ('1150', 'Zone-L11-C', 'open_plan'),
    ('1151', 'Zone-L11-C', 'corner'), ('1152', 'Zone-L11-C', 'near_window'), ('1153', 'Zone-L11-C', 'near_diffuser'), ('1154', 'Zone-L11-C', 'near_printer'), ('1155', 'Zone-L11-C', 'open_plan'),
    ('1156', 'Zone-L11-C', 'corner'), ('1157', 'Zone-L11-C', 'near_window'), ('1158', 'Zone-L11-C', 'near_diffuser'), ('1159', 'Zone-L11-C', 'near_printer'), ('1160', 'Zone-L11-C', 'open_plan'),
    -- Zone D (1161-1180)
    ('1161', 'Zone-L11-D', 'open_plan'), ('1162', 'Zone-L11-D', 'corner'), ('1163', 'Zone-L11-D', 'near_window'), ('1164', 'Zone-L11-D', 'near_diffuser'), ('1165', 'Zone-L11-D', 'near_printer'),
    ('1166', 'Zone-L11-D', 'open_plan'), ('1167', 'Zone-L11-D', 'corner'), ('1168', 'Zone-L11-D', 'near_window'), ('1169', 'Zone-L11-D', 'near_diffuser'), ('1170', 'Zone-L11-D', 'near_printer'),
    ('1171', 'Zone-L11-D', 'open_plan'), ('1172', 'Zone-L11-D', 'corner'), ('1173', 'Zone-L11-D', 'near_window'), ('1174', 'Zone-L11-D', 'near_diffuser'), ('1175', 'Zone-L11-D', 'near_printer'),
    ('1176', 'Zone-L11-D', 'open_plan'), ('1177', 'Zone-L11-D', 'corner'), ('1178', 'Zone-L11-D', 'near_window'), ('1179', 'Zone-L11-D', 'near_diffuser'), ('1180', 'Zone-L11-D', 'near_printer'),
    -- Zone E (1181-1200)
    ('1181', 'Zone-L11-E', 'near_printer'), ('1182', 'Zone-L11-E', 'open_plan'), ('1183', 'Zone-L11-E', 'corner'), ('1184', 'Zone-L11-E', 'near_window'), ('1185', 'Zone-L11-E', 'near_diffuser'),
    ('1186', 'Zone-L11-E', 'near_printer'), ('1187', 'Zone-L11-E', 'open_plan'), ('1188', 'Zone-L11-E', 'corner'), ('1189', 'Zone-L11-E', 'near_window'), ('1190', 'Zone-L11-E', 'near_diffuser'),
    ('1191', 'Zone-L11-E', 'near_printer'), ('1192', 'Zone-L11-E', 'open_plan'), ('1193', 'Zone-L11-E', 'corner'), ('1194', 'Zone-L11-E', 'near_window'), ('1195', 'Zone-L11-E', 'near_diffuser'),
    ('1196', 'Zone-L11-E', 'near_printer'), ('1197', 'Zone-L11-E', 'open_plan'), ('1198', 'Zone-L11-E', 'corner'), ('1199', 'Zone-L11-E', 'near_window'), ('1200', 'Zone-L11-E', 'near_diffuser')
) AS d(desk_id, zone_id, context)
JOIN hvac_zones hz ON hz.zone_id = d.zone_id
ON CONFLICT (desk_id) DO UPDATE SET
  hvac_zone_id = EXCLUDED.hvac_zone_id,
  updated_at = NOW();

-- Level 12 desks (1201-1300)
INSERT INTO desks (desk_id, building_id, floor, hvac_zone_id, near_diffuser, near_printer, near_window)
SELECT
  d.desk_id,
  '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9'::UUID,
  'L12',
  hz.id,
  d.context = 'near_diffuser',
  d.context = 'near_printer',
  d.context = 'near_window'
FROM (
  VALUES
    -- Zone A (1201-1220)
    ('1201', 'Zone-L12-A', 'near_diffuser'), ('1202', 'Zone-L12-A', 'near_printer'), ('1203', 'Zone-L12-A', 'open_plan'), ('1204', 'Zone-L12-A', 'corner'), ('1205', 'Zone-L12-A', 'near_window'),
    ('1206', 'Zone-L12-A', 'near_diffuser'), ('1207', 'Zone-L12-A', 'near_printer'), ('1208', 'Zone-L12-A', 'open_plan'), ('1209', 'Zone-L12-A', 'corner'), ('1210', 'Zone-L12-A', 'near_window'),
    ('1211', 'Zone-L12-A', 'near_diffuser'), ('1212', 'Zone-L12-A', 'near_printer'), ('1213', 'Zone-L12-A', 'open_plan'), ('1214', 'Zone-L12-A', 'corner'), ('1215', 'Zone-L12-A', 'near_window'),
    ('1216', 'Zone-L12-A', 'near_diffuser'), ('1217', 'Zone-L12-A', 'near_printer'), ('1218', 'Zone-L12-A', 'open_plan'), ('1219', 'Zone-L12-A', 'corner'), ('1220', 'Zone-L12-A', 'near_window'),
    -- Zone B (1221-1240)
    ('1221', 'Zone-L12-B', 'near_window'), ('1222', 'Zone-L12-B', 'near_diffuser'), ('1223', 'Zone-L12-B', 'near_printer'), ('1224', 'Zone-L12-B', 'open_plan'), ('1225', 'Zone-L12-B', 'corner'),
    ('1226', 'Zone-L12-B', 'near_window'), ('1227', 'Zone-L12-B', 'near_diffuser'), ('1228', 'Zone-L12-B', 'near_printer'), ('1229', 'Zone-L12-B', 'open_plan'), ('1230', 'Zone-L12-B', 'corner'),
    ('1231', 'Zone-L12-B', 'near_window'), ('1232', 'Zone-L12-B', 'near_diffuser'), ('1233', 'Zone-L12-B', 'near_printer'), ('1234', 'Zone-L12-B', 'open_plan'), ('1235', 'Zone-L12-B', 'corner'),
    ('1236', 'Zone-L12-B', 'near_window'), ('1237', 'Zone-L12-B', 'near_diffuser'), ('1238', 'Zone-L12-B', 'near_printer'), ('1239', 'Zone-L12-B', 'open_plan'), ('1240', 'Zone-L12-B', 'corner'),
    -- Zone C (1241-1260)
    ('1241', 'Zone-L12-C', 'corner'), ('1242', 'Zone-L12-C', 'near_window'), ('1243', 'Zone-L12-C', 'near_diffuser'), ('1244', 'Zone-L12-C', 'near_printer'), ('1245', 'Zone-L12-C', 'open_plan'),
    ('1246', 'Zone-L12-C', 'corner'), ('1247', 'Zone-L12-C', 'near_window'), ('1248', 'Zone-L12-C', 'near_diffuser'), ('1249', 'Zone-L12-C', 'near_printer'), ('1250', 'Zone-L12-C', 'open_plan'),
    ('1251', 'Zone-L12-C', 'corner'), ('1252', 'Zone-L12-C', 'near_window'), ('1253', 'Zone-L12-C', 'near_diffuser'), ('1254', 'Zone-L12-C', 'near_printer'), ('1255', 'Zone-L12-C', 'open_plan'),
    ('1256', 'Zone-L12-C', 'corner'), ('1257', 'Zone-L12-C', 'near_window'), ('1258', 'Zone-L12-C', 'near_diffuser'), ('1259', 'Zone-L12-C', 'near_printer'), ('1260', 'Zone-L12-C', 'open_plan'),
    -- Zone D (1261-1280)
    ('1261', 'Zone-L12-D', 'open_plan'), ('1262', 'Zone-L12-D', 'corner'), ('1263', 'Zone-L12-D', 'near_window'), ('1264', 'Zone-L12-D', 'near_diffuser'), ('1265', 'Zone-L12-D', 'near_printer'),
    ('1266', 'Zone-L12-D', 'open_plan'), ('1267', 'Zone-L12-D', 'corner'), ('1268', 'Zone-L12-D', 'near_window'), ('1269', 'Zone-L12-D', 'near_diffuser'), ('1270', 'Zone-L12-D', 'near_printer'),
    ('1271', 'Zone-L12-D', 'open_plan'), ('1272', 'Zone-L12-D', 'corner'), ('1273', 'Zone-L12-D', 'near_window'), ('1274', 'Zone-L12-D', 'near_diffuser'), ('1275', 'Zone-L12-D', 'near_printer'),
    ('1276', 'Zone-L12-D', 'open_plan'), ('1277', 'Zone-L12-D', 'corner'), ('1278', 'Zone-L12-D', 'near_window'), ('1279', 'Zone-L12-D', 'near_diffuser'), ('1280', 'Zone-L12-D', 'near_printer'),
    -- Zone E (1281-1300)
    ('1281', 'Zone-L12-E', 'near_printer'), ('1282', 'Zone-L12-E', 'open_plan'), ('1283', 'Zone-L12-E', 'corner'), ('1284', 'Zone-L12-E', 'near_window'), ('1285', 'Zone-L12-E', 'near_diffuser'),
    ('1286', 'Zone-L12-E', 'near_printer'), ('1287', 'Zone-L12-E', 'open_plan'), ('1288', 'Zone-L12-E', 'corner'), ('1289', 'Zone-L12-E', 'near_window'), ('1290', 'Zone-L12-E', 'near_diffuser'),
    ('1291', 'Zone-L12-E', 'near_printer'), ('1292', 'Zone-L12-E', 'open_plan'), ('1293', 'Zone-L12-E', 'corner'), ('1294', 'Zone-L12-E', 'near_window'), ('1295', 'Zone-L12-E', 'near_diffuser'),
    ('1296', 'Zone-L12-E', 'near_printer'), ('1297', 'Zone-L12-E', 'open_plan'), ('1298', 'Zone-L12-E', 'corner'), ('1299', 'Zone-L12-E', 'near_window'), ('1300', 'Zone-L12-E', 'near_diffuser')
) AS d(desk_id, zone_id, context)
JOIN hvac_zones hz ON hz.zone_id = d.zone_id
ON CONFLICT (desk_id) DO UPDATE SET
  hvac_zone_id = EXCLUDED.hvac_zone_id,
  updated_at = NOW();

-- =====================================================
-- DALI CONTROLLERS (57 controllers: 20 on L12, 19 on L11, 18 on L10)
-- =====================================================
INSERT INTO dali_controllers (controller_id, name, location, ip_address, bacnet_device_id, channels, site_id, status, firmware_version)
VALUES
  -- Level 12 (20 controllers)
  ('DALI-L12-01', 'Level 12 North A', 'DB Room L12', '192.168.10.51', 100001, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-02', 'Level 12 North B', 'DB Room L12', '192.168.10.52', 100002, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-03', 'Level 12 North C', 'DB Room L12', '192.168.10.53', 100003, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-04', 'Level 12 South A', 'DB Room L12', '192.168.10.54', 100004, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-05', 'Level 12 South B', 'DB Room L12', '192.168.10.55', 100005, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-06', 'Level 12 South C', 'DB Room L12', '192.168.10.56', 100006, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-07', 'Level 12 East', 'DB Room L12', '192.168.10.57', 100007, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-08', 'Level 12 West', 'DB Room L12', '192.168.10.58', 100008, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-09', 'Level 12 Meeting Rooms', 'DB Room L12', '192.168.10.59', 100009, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-10', 'Level 12 Executive', 'DB Room L12', '192.168.10.60', 100010, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-11', 'Level 12 Core A', 'DB Room L12', '192.168.10.61', 100011, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-12', 'Level 12 Core B', 'DB Room L12', '192.168.10.62', 100012, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-13', 'Level 12 Reception', 'DB Room L12', '192.168.10.63', 100013, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-14', 'Level 12 Break Area', 'DB Room L12', '192.168.10.64', 100014, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-15', 'Level 12 Corridor A', 'DB Room L12', '192.168.10.65', 100015, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-16', 'Level 12 Corridor B', 'DB Room L12', '192.168.10.66', 100016, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-17', 'Level 12 Server Room', 'DB Room L12', '192.168.10.67', 100017, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-18', 'Level 12 Training', 'DB Room L12', '192.168.10.68', 100018, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-19', 'Level 12 Board Room', 'DB Room L12', '192.168.10.69', 100019, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L12-20', 'Level 12 Emergency', 'DB Room L12', '192.168.10.70', 100020, 3, 'site-002', 'degraded', '3.2.0'),
  -- Level 11 (19 controllers)
  ('DALI-L11-01', 'Level 11 North A', 'DB Room L11', '192.168.10.71', 100021, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-02', 'Level 11 North B', 'DB Room L11', '192.168.10.72', 100022, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-03', 'Level 11 North C', 'DB Room L11', '192.168.10.73', 100023, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-04', 'Level 11 South A', 'DB Room L11', '192.168.10.74', 100024, 3, 'site-002', 'offline', '3.2.1'),
  ('DALI-L11-05', 'Level 11 South B', 'DB Room L11', '192.168.10.75', 100025, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-06', 'Level 11 South C', 'DB Room L11', '192.168.10.76', 100026, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-07', 'Level 11 East', 'DB Room L11', '192.168.10.77', 100027, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-08', 'Level 11 West', 'DB Room L11', '192.168.10.78', 100028, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-09', 'Level 11 Meeting Rooms', 'DB Room L11', '192.168.10.79', 100029, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-10', 'Level 11 Open Plan Central', 'DB Room L11', '192.168.10.80', 100030, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-11', 'Level 11 Core A', 'DB Room L11', '192.168.10.81', 100031, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-12', 'Level 11 Core B', 'DB Room L11', '192.168.10.82', 100032, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-13', 'Level 11 Kitchen', 'DB Room L11', '192.168.10.83', 100033, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-14', 'Level 11 Print Area', 'DB Room L11', '192.168.10.84', 100034, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-15', 'Level 11 Corridor A', 'DB Room L11', '192.168.10.85', 100035, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-16', 'Level 11 Corridor B', 'DB Room L11', '192.168.10.86', 100036, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-17', 'Level 11 Storage', 'DB Room L11', '192.168.10.87', 100037, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-18', 'Level 11 Wellness', 'DB Room L11', '192.168.10.88', 100038, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L11-19', 'Level 11 Emergency', 'DB Room L11', '192.168.10.89', 100039, 3, 'site-002', 'online', '3.2.1'),
  -- Level 10 (18 controllers)
  ('DALI-L10-01', 'Level 10 North A', 'DB Room L10', '192.168.10.91', 100040, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-02', 'Level 10 North B', 'DB Room L10', '192.168.10.92', 100041, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-03', 'Level 10 North C', 'DB Room L10', '192.168.10.93', 100042, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-04', 'Level 10 South A', 'DB Room L10', '192.168.10.94', 100043, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-05', 'Level 10 South B', 'DB Room L10', '192.168.10.95', 100044, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-06', 'Level 10 South C', 'DB Room L10', '192.168.10.96', 100045, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-07', 'Level 10 East', 'DB Room L10', '192.168.10.97', 100046, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-08', 'Level 10 West', 'DB Room L10', '192.168.10.98', 100047, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-09', 'Level 10 Meeting Rooms', 'DB Room L10', '192.168.10.99', 100048, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-10', 'Level 10 Open Plan Central', 'DB Room L10', '192.168.10.100', 100049, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-11', 'Level 10 Core A', 'DB Room L10', '192.168.10.101', 100050, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-12', 'Level 10 Core B', 'DB Room L10', '192.168.10.102', 100051, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-13', 'Level 10 Reception', 'DB Room L10', '192.168.10.103', 100052, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-14', 'Level 10 Break Area', 'DB Room L10', '192.168.10.104', 100053, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-15', 'Level 10 Corridor A', 'DB Room L10', '192.168.10.105', 100054, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-16', 'Level 10 Corridor B', 'DB Room L10', '192.168.10.106', 100055, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-17', 'Level 10 Storage', 'DB Room L10', '192.168.10.107', 100056, 3, 'site-002', 'online', '3.2.1'),
  ('DALI-L10-18', 'Level 10 Emergency', 'DB Room L10', '192.168.10.108', 100057, 3, 'site-002', 'online', '3.2.1')
ON CONFLICT (controller_id) DO UPDATE SET
  status = EXCLUDED.status,
  firmware_version = EXCLUDED.firmware_version,
  updated_at = NOW();

-- =====================================================
-- DALI ZONES (10 lighting zones)
-- =====================================================
INSERT INTO dali_zones (zone_id, name, floor, site_id, area_sqm, desk_count)
VALUES
  ('Zone-L12-N', 'Level 12 North Open Plan', 'L12', 'site-002', 450, 45),
  ('Zone-L12-S', 'Level 12 South Open Plan', 'L12', 'site-002', 380, 38),
  ('Zone-L12-MR', 'Level 12 Meeting Rooms', 'L12', 'site-002', 120, 0),
  ('Zone-L12-EX', 'Level 12 Executive', 'L12', 'site-002', 150, 8),
  ('Zone-L11-N', 'Level 11 North Open Plan', 'L11', 'site-002', 480, 48),
  ('Zone-L11-S', 'Level 11 South Open Plan (Unoccupied Wing)', 'L11', 'site-002', 420, 42),
  ('Zone-L11-MR', 'Level 11 Meeting Rooms', 'L11', 'site-002', 100, 0),
  ('Zone-L10-N', 'Level 10 North Open Plan', 'L10', 'site-002', 400, 40),
  ('Zone-L10-S', 'Level 10 South Open Plan', 'L10', 'site-002', 350, 35),
  ('Zone-L10-MR', 'Level 10 Meeting Rooms', 'L10', 'site-002', 90, 0)
ON CONFLICT (zone_id) DO UPDATE SET
  name = EXCLUDED.name,
  updated_at = NOW();

-- =====================================================
-- DALI LUMINAIRES (32 sample luminaires including 2 faulty)
-- =====================================================
INSERT INTO dali_luminaires (controller_id, luminaire_id, dali_address, channel, name, location, zone_id, wattage, current_level, power_consumption, operating_hours, fault_status)
SELECT
  c.id,
  l.luminaire_id,
  l.dali_address,
  l.channel,
  l.name,
  l.location,
  l.zone_id,
  l.wattage,
  l.current_level,
  l.power_consumption,
  l.operating_hours,
  l.fault_status
FROM (
  VALUES
    ('DALI-L12-01', 'LUM-L12-N-001', 1, 1, 'Panel L12 North Row 1', 'Above Desk 1-4', 'Zone-L12-N', 35, 75, 26.25, 24500, false),
    ('DALI-L12-01', 'LUM-L12-N-002', 2, 1, 'Panel L12 North Row 2', 'Above Desk 5-8', 'Zone-L12-N', 35, 70, 24.5, 24500, false),
    ('DALI-L12-01', 'LUM-L12-N-003', 3, 1, 'Panel L12 North Row 3', 'Above Desk 9-12', 'Zone-L12-N', 35, 80, 28.0, 24500, false),
    ('DALI-L12-02', 'LUM-L12-N-004', 1, 1, 'Panel L12 North Row 4', 'Above Desk 13-16', 'Zone-L12-N', 35, 65, 22.75, 24500, false),
    ('DALI-L12-02', 'LUM-L12-N-005', 2, 1, 'Panel L12 North Row 5', 'Above Desk 17-20', 'Zone-L12-N', 35, 72, 25.2, 24500, false),
    ('DALI-L12-04', 'LUM-L12-S-001', 1, 1, 'Panel L12 South Row 1', 'Above Desk 51-54', 'Zone-L12-S', 35, 68, 23.8, 23800, false),
    ('DALI-L12-04', 'LUM-L12-S-002', 2, 1, 'Panel L12 South Row 2', 'Above Desk 55-58', 'Zone-L12-S', 35, 74, 25.9, 23800, false),
    ('DALI-L12-04', 'LUM-L12-S-003', 3, 1, 'Panel L12 South Row 3', 'Above Desk 59-62', 'Zone-L12-S', 35, 70, 24.5, 23800, false),
    ('DALI-L12-09', 'LUM-L12-MR-001', 1, 1, 'Meeting Room 1 Main', 'Meeting Room 1 Center', 'Zone-L12-MR', 45, 100, 45.0, 12500, false),
    ('DALI-L12-09', 'LUM-L12-MR-002', 2, 1, 'Meeting Room 2 Main', 'Meeting Room 2 Center', 'Zone-L12-MR', 45, 0, 0.0, 11200, false),
    ('DALI-L12-09', 'LUM-L12-MR-003', 3, 1, 'Meeting Room 3 Main', 'Meeting Room 3 Center', 'Zone-L12-MR', 45, 0, 0.0, 10800, false),
    ('DALI-L12-09', 'LUM-L12-MR-004', 4, 1, 'Board Room Feature', 'Board Room', 'Zone-L12-MR', 60, 85, 51.0, 8500, false),
    ('DALI-L12-10', 'LUM-L12-EX-001', 1, 1, 'Executive Office 1', 'Executive Office 1', 'Zone-L12-EX', 40, 90, 36.0, 9200, false),
    ('DALI-L12-10', 'LUM-L12-EX-002', 2, 1, 'Executive Office 2', 'Executive Office 2', 'Zone-L12-EX', 40, 0, 0.0, 8800, false),
    ('DALI-L11-01', 'LUM-L11-N-001', 1, 1, 'Panel L11 North Row 1', 'Above Desk 1-4', 'Zone-L11-N', 35, 72, 25.2, 22100, false),
    ('DALI-L11-01', 'LUM-L11-N-002', 2, 1, 'Panel L11 North Row 2', 'Above Desk 5-8', 'Zone-L11-N', 35, 68, 23.8, 22100, false),
    ('DALI-L11-01', 'LUM-L11-N-003', 3, 1, 'Panel L11 North Row 3', 'Above Desk 9-12', 'Zone-L11-N', 35, 75, 26.25, 22100, false),
    ('DALI-L11-04', 'LUM-L11-S-001', 1, 1, 'Panel L11 South Row 1', 'Above Desk 51-54 (UNOCCUPIED)', 'Zone-L11-S', 35, 100, 35.0, 21500, false),
    ('DALI-L11-04', 'LUM-L11-S-002', 2, 1, 'Panel L11 South Row 2', 'Above Desk 55-58 (UNOCCUPIED)', 'Zone-L11-S', 35, 100, 35.0, 21500, false),
    ('DALI-L11-04', 'LUM-L11-S-003', 3, 1, 'Panel L11 South Row 3', 'Above Desk 59-62 (UNOCCUPIED)', 'Zone-L11-S', 35, 100, 35.0, 21500, false),
    ('DALI-L11-09', 'LUM-L11-MR-001', 1, 1, 'Meeting Room 1 Main L11', 'Meeting Room 1 Center', 'Zone-L11-MR', 45, 95, 42.75, 11800, false),
    ('DALI-L11-09', 'LUM-L11-MR-002', 2, 1, 'Meeting Room 2 Main L11', 'Meeting Room 2 Center', 'Zone-L11-MR', 45, 0, 0.0, 10500, false),
    ('DALI-L10-01', 'LUM-L10-N-001', 1, 1, 'Panel L10 North Row 1', 'Above Desk 1-4', 'Zone-L10-N', 35, 70, 24.5, 20200, false),
    ('DALI-L10-01', 'LUM-L10-N-002', 2, 1, 'Panel L10 North Row 2', 'Above Desk 5-8', 'Zone-L10-N', 35, 65, 22.75, 20200, false),
    ('DALI-L10-01', 'LUM-L10-N-003', 3, 1, 'Panel L10 North Row 3', 'Above Desk 9-12', 'Zone-L10-N', 35, 78, 27.3, 20200, false),
    ('DALI-L10-04', 'LUM-L10-S-001', 1, 1, 'Panel L10 South Row 1', 'Above Desk 51-54', 'Zone-L10-S', 35, 72, 25.2, 19800, false),
    ('DALI-L10-04', 'LUM-L10-S-002', 2, 1, 'Panel L10 South Row 2', 'Above Desk 55-58', 'Zone-L10-S', 35, 68, 23.8, 19800, false),
    ('DALI-L10-09', 'LUM-L10-MR-001', 1, 1, 'Meeting Room 1 Main L10', 'Meeting Room 1 Center', 'Zone-L10-MR', 45, 100, 45.0, 10200, false),
    ('DALI-L10-09', 'LUM-L10-MR-002', 2, 1, 'Meeting Room 2 Main L10', 'Meeting Room 2 Center', 'Zone-L10-MR', 45, 0, 0.0, 9500, false),
    ('DALI-L10-09', 'LUM-L10-MR-003', 3, 1, 'Meeting Room 3 Main L10', 'Meeting Room 3 Center', 'Zone-L10-MR', 45, 88, 39.6, 9200, false),
    -- Faulty luminaires for demo
    ('DALI-L12-03', 'LUM-L12-FAULT-001', 15, 2, 'Panel L12 North Faulty', 'Above Desk 45-48', 'Zone-L12-N', 35, 0, 0.0, 28500, true),
    ('DALI-L11-05', 'LUM-L11-FAULT-001', 12, 2, 'Panel L11 South Faulty', 'Above Desk 70-73', 'Zone-L11-S', 35, 0, 0.0, 26800, true)
) AS l(controller_id, luminaire_id, dali_address, channel, name, location, zone_id, wattage, current_level, power_consumption, operating_hours, fault_status)
JOIN dali_controllers c ON c.controller_id = l.controller_id
ON CONFLICT (luminaire_id) DO UPDATE SET
  current_level = EXCLUDED.current_level,
  power_consumption = EXCLUDED.power_consumption,
  fault_status = EXCLUDED.fault_status,
  last_updated = NOW();

-- =====================================================
-- DALI SENSORS (46 sample sensors including 1 faulty)
-- =====================================================
INSERT INTO dali_sensors (controller_id, sensor_id, dali_address, channel, location, zone_id, desk_id, has_pir, has_daylight, occupancy, lux_level, fault_status)
SELECT
  c.id,
  s.sensor_id,
  s.dali_address,
  s.channel,
  s.location,
  s.zone_id,
  s.desk_id,
  s.has_pir,
  s.has_daylight,
  s.occupancy,
  s.lux_level,
  s.fault_status
FROM (
  VALUES
    -- Level 12 North sensors
    ('DALI-L12-01', 'PIR-L12-N-001', 1, 1, 'Desk 1, Level 12 North', 'Zone-L12-N', 'L12-D001', true, true, true, 450.0, false),
    ('DALI-L12-01', 'PIR-L12-N-002', 2, 1, 'Desk 2, Level 12 North', 'Zone-L12-N', 'L12-D002', true, true, true, 480.0, false),
    ('DALI-L12-01', 'PIR-L12-N-003', 3, 1, 'Desk 3, Level 12 North', 'Zone-L12-N', 'L12-D003', true, true, false, 520.0, false),
    ('DALI-L12-01', 'PIR-L12-N-004', 4, 1, 'Desk 4, Level 12 North', 'Zone-L12-N', 'L12-D004', true, true, true, 390.0, false),
    ('DALI-L12-01', 'PIR-L12-N-005', 5, 1, 'Desk 5, Level 12 North', 'Zone-L12-N', 'L12-D005', true, true, false, 510.0, false),
    ('DALI-L12-01', 'PIR-L12-N-006', 6, 1, 'Desk 6, Level 12 North', 'Zone-L12-N', 'L12-D006', true, true, true, 465.0, false),
    ('DALI-L12-02', 'PIR-L12-N-007', 1, 1, 'Desk 7, Level 12 North', 'Zone-L12-N', 'L12-D007', true, true, true, 445.0, false),
    ('DALI-L12-02', 'PIR-L12-N-008', 2, 1, 'Desk 8, Level 12 North', 'Zone-L12-N', 'L12-D008', true, true, false, 530.0, false),
    ('DALI-L12-02', 'PIR-L12-N-009', 3, 1, 'Desk 9, Level 12 North', 'Zone-L12-N', 'L12-D009', true, true, true, 420.0, false),
    ('DALI-L12-02', 'PIR-L12-N-010', 4, 1, 'Desk 10, Level 12 North', 'Zone-L12-N', 'L12-D010', true, true, true, 475.0, false),
    -- Level 12 South sensors
    ('DALI-L12-04', 'PIR-L12-S-001', 1, 1, 'Desk 1, Level 12 South', 'Zone-L12-S', 'L12-D051', true, true, true, 380.0, false),
    ('DALI-L12-04', 'PIR-L12-S-002', 2, 1, 'Desk 2, Level 12 South', 'Zone-L12-S', 'L12-D052', true, true, false, 410.0, false),
    ('DALI-L12-04', 'PIR-L12-S-003', 3, 1, 'Desk 3, Level 12 South', 'Zone-L12-S', 'L12-D053', true, true, true, 395.0, false),
    ('DALI-L12-04', 'PIR-L12-S-004', 4, 1, 'Desk 4, Level 12 South', 'Zone-L12-S', 'L12-D054', true, true, false, 420.0, false),
    ('DALI-L12-04', 'PIR-L12-S-005', 5, 1, 'Desk 5, Level 12 South', 'Zone-L12-S', 'L12-D055', true, true, true, 365.0, false),
    -- Level 12 Meeting Rooms
    ('DALI-L12-09', 'PIR-L12-MR-001', 1, 1, 'Meeting Room 1, Level 12', 'Zone-L12-MR', NULL, true, true, true, 320.0, false),
    ('DALI-L12-09', 'PIR-L12-MR-002', 2, 1, 'Meeting Room 2, Level 12', 'Zone-L12-MR', NULL, true, true, false, 285.0, false),
    ('DALI-L12-09', 'PIR-L12-MR-003', 3, 1, 'Meeting Room 3, Level 12', 'Zone-L12-MR', NULL, true, true, false, 290.0, false),
    ('DALI-L12-09', 'PIR-L12-MR-004', 4, 1, 'Board Room, Level 12', 'Zone-L12-MR', NULL, true, true, true, 350.0, false),
    -- Level 12 Executive
    ('DALI-L12-10', 'PIR-L12-EX-001', 1, 1, 'Executive Office 1, Level 12', 'Zone-L12-EX', 'L12-EX01', true, true, true, 400.0, false),
    ('DALI-L12-10', 'PIR-L12-EX-002', 2, 1, 'Executive Office 2, Level 12', 'Zone-L12-EX', 'L12-EX02', true, true, false, 380.0, false),
    -- Level 11 North sensors
    ('DALI-L11-01', 'PIR-L11-N-001', 1, 1, 'Desk 1, Level 11 North', 'Zone-L11-N', 'L11-D001', true, true, true, 440.0, false),
    ('DALI-L11-01', 'PIR-L11-N-002', 2, 1, 'Desk 2, Level 11 North', 'Zone-L11-N', 'L11-D002', true, true, true, 470.0, false),
    ('DALI-L11-01', 'PIR-L11-N-003', 3, 1, 'Desk 3, Level 11 North', 'Zone-L11-N', 'L11-D003', true, true, false, 510.0, false),
    ('DALI-L11-01', 'PIR-L11-N-004', 4, 1, 'Desk 4, Level 11 North', 'Zone-L11-N', 'L11-D004', true, true, true, 385.0, false),
    ('DALI-L11-01', 'PIR-L11-N-005', 5, 1, 'Desk 5, Level 11 North', 'Zone-L11-N', 'L11-D005', true, true, true, 495.0, false),
    ('DALI-L11-01', 'PIR-L11-N-006', 6, 1, 'Desk 6, Level 11 North', 'Zone-L11-N', 'L11-D006', true, true, false, 455.0, false),
    -- Level 11 South sensors (unoccupied wing - ENERGY WASTE DEMO)
    ('DALI-L11-04', 'PIR-L11-S-001', 1, 1, 'Desk 1, Level 11 South', 'Zone-L11-S', 'L11-D051', true, true, false, 620.0, false),
    ('DALI-L11-04', 'PIR-L11-S-002', 2, 1, 'Desk 2, Level 11 South', 'Zone-L11-S', 'L11-D052', true, true, false, 650.0, false),
    ('DALI-L11-04', 'PIR-L11-S-003', 3, 1, 'Desk 3, Level 11 South', 'Zone-L11-S', 'L11-D053', true, true, false, 580.0, false),
    ('DALI-L11-04', 'PIR-L11-S-004', 4, 1, 'Desk 4, Level 11 South', 'Zone-L11-S', 'L11-D054', true, true, false, 610.0, false),
    ('DALI-L11-04', 'PIR-L11-S-005', 5, 1, 'Desk 5, Level 11 South', 'Zone-L11-S', 'L11-D055', true, true, false, 640.0, false),
    -- Level 11 Meeting Rooms
    ('DALI-L11-09', 'PIR-L11-MR-001', 1, 1, 'Meeting Room 1, Level 11', 'Zone-L11-MR', NULL, true, true, true, 310.0, false),
    ('DALI-L11-09', 'PIR-L11-MR-002', 2, 1, 'Meeting Room 2, Level 11', 'Zone-L11-MR', NULL, true, true, false, 275.0, false),
    -- Level 10 North sensors
    ('DALI-L10-01', 'PIR-L10-N-001', 1, 1, 'Desk 1, Level 10 North', 'Zone-L10-N', 'L10-D001', true, true, true, 430.0, false),
    ('DALI-L10-01', 'PIR-L10-N-002', 2, 1, 'Desk 2, Level 10 North', 'Zone-L10-N', 'L10-D002', true, true, false, 460.0, false),
    ('DALI-L10-01', 'PIR-L10-N-003', 3, 1, 'Desk 3, Level 10 North', 'Zone-L10-N', 'L10-D003', true, true, true, 490.0, false),
    ('DALI-L10-01', 'PIR-L10-N-004', 4, 1, 'Desk 4, Level 10 North', 'Zone-L10-N', 'L10-D004', true, true, true, 375.0, false),
    -- Level 10 South sensors
    ('DALI-L10-04', 'PIR-L10-S-001', 1, 1, 'Desk 1, Level 10 South', 'Zone-L10-S', 'L10-D051', true, true, true, 360.0, false),
    ('DALI-L10-04', 'PIR-L10-S-002', 2, 1, 'Desk 2, Level 10 South', 'Zone-L10-S', 'L10-D052', true, true, false, 400.0, false),
    ('DALI-L10-04', 'PIR-L10-S-003', 3, 1, 'Desk 3, Level 10 South', 'Zone-L10-S', 'L10-D053', true, true, true, 385.0, false),
    -- Level 10 Meeting Rooms
    ('DALI-L10-09', 'PIR-L10-MR-001', 1, 1, 'Meeting Room 1, Level 10', 'Zone-L10-MR', NULL, true, true, true, 300.0, false),
    ('DALI-L10-09', 'PIR-L10-MR-002', 2, 1, 'Meeting Room 2, Level 10', 'Zone-L10-MR', NULL, true, true, false, 265.0, false),
    ('DALI-L10-09', 'PIR-L10-MR-003', 3, 1, 'Meeting Room 3, Level 10', 'Zone-L10-MR', NULL, true, true, true, 325.0, false),
    -- Faulty sensor for demo
    ('DALI-L12-03', 'PIR-L12-FAULT-001', 10, 2, 'Desk F1, Level 12 North', 'Zone-L12-N', 'L12-D045', true, true, false, 0.0, true)
) AS s(controller_id, sensor_id, dali_address, channel, location, zone_id, desk_id, has_pir, has_daylight, occupancy, lux_level, fault_status)
JOIN dali_controllers c ON c.controller_id = s.controller_id
ON CONFLICT (sensor_id) DO UPDATE SET
  occupancy = EXCLUDED.occupancy,
  lux_level = EXCLUDED.lux_level,
  fault_status = EXCLUDED.fault_status,
  last_updated = NOW();

-- =====================================================
-- Summary
-- =====================================================
DO $$
DECLARE
  zone_count INTEGER;
  desk_count INTEGER;
  controller_count INTEGER;
  dali_zone_count INTEGER;
  luminaire_count INTEGER;
  sensor_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO zone_count FROM hvac_zones WHERE building_id = '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9';
  SELECT COUNT(*) INTO desk_count FROM desks WHERE building_id = '50a24fb7-80f3-5e0b-9aa3-bf0939b923d9';
  SELECT COUNT(*) INTO controller_count FROM dali_controllers WHERE site_id = 'site-002';
  SELECT COUNT(*) INTO dali_zone_count FROM dali_zones WHERE site_id = 'site-002';
  SELECT COUNT(*) INTO luminaire_count FROM dali_luminaires l JOIN dali_controllers c ON l.controller_id = c.id WHERE c.site_id = 'site-002';
  SELECT COUNT(*) INTO sensor_count FROM dali_sensors s JOIN dali_controllers c ON s.controller_id = c.id WHERE c.site_id = 'site-002';

  RAISE NOTICE 'Sandton seed complete:';
  RAISE NOTICE '  HVAC Zones: %', zone_count;
  RAISE NOTICE '  Desks: %', desk_count;
  RAISE NOTICE '  DALI Controllers: %', controller_count;
  RAISE NOTICE '  DALI Zones: %', dali_zone_count;
  RAISE NOTICE '  DALI Luminaires: %', luminaire_count;
  RAISE NOTICE '  DALI Sensors: %', sensor_count;
END $$;
