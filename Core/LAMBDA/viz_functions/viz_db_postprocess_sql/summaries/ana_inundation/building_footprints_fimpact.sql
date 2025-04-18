--------------- Building Footprints ---------------
DROP TABLE IF EXISTS publish.ana_inundation_building_footprints;
CREATE INDEX IF NOT EXISTS idx_building_geom ON external.building_footprints_fema USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_inundation_geo_geom ON fim_ingest.ana_inundation_geo USING GIST (geom);
ANALYZE external.building_footprints_fema;
ANALYZE fim_ingest.ana_inundation_geo;
SELECT
	buildings.build_id,
    buildings.occ_cls,
    buildings.prim_occ,
    buildings.prop_st,
    buildings.sqfeet,
    buildings.height,
    buildings.censuscode,
    buildings.prod_date,
    buildings.source,
    buildings.val_method,
    flows.hydro_id,
	flows.hydro_id::TEXT AS hydro_id_str,
	flows.feature_id,
	flows.feature_id::TEXT AS feature_id_str,
	flows.discharge_cfs AS streamflow_cfs,
	fim.rc_stage_ft AS fim_stage_ft,
    buildings.geom,
	ST_Centroid(buildings.geom) as geom_xy
INTO publish.ana_inundation_building_footprints
FROM external.building_footprints_fema as buildings
JOIN fim_ingest.ana_inundation_geo fim_geo ON ST_INTERSECTS(fim_geo.geom, buildings.geom)
JOIN fim_ingest.ana_inundation_flows flows ON fim_geo.hand_id = flows.hand_id
JOIN fim_ingest.ana_inundation fim ON fim_geo.hand_id = fim.hand_id;

--------------- County Summary ---------------
DROP TABLE IF EXISTS publish.ana_inundation_counties;
SELECT
	counties.geoid,
	counties.name as county,
	buildings.prop_st as state,
	max(fim.streamflow_cfs) AS max_flow_cfs,
	avg(fim.streamflow_cfs) AS avg_flow_cfs,
	max(fim.fim_stage_ft) AS max_fim_stage_ft,
	avg(fim.fim_stage_ft) AS avg_fim_stage_ft,
	count(buildings.build_id) AS buildings_impacted,
	sum(buildings.sqfeet) AS building_sqft_impacted,
	sum(CASE WHEN buildings.occ_cls = 'Agriculture' THEN 1 ELSE 0 END) AS bldgs_agriculture,
	sum(CASE WHEN buildings.occ_cls = 'Assembly' THEN 1 ELSE 0 END) AS bldgs_assembly,
	sum(CASE WHEN buildings.occ_cls = 'Commercial' THEN 1 ELSE 0 END) AS bldgs_commercial,
	sum(CASE WHEN buildings.occ_cls = 'Education' THEN 1 ELSE 0 END) AS bldgs_education,
	sum(CASE WHEN buildings.occ_cls = 'Government' THEN 1 ELSE 0 END) AS bldgs_government,
	sum(CASE WHEN buildings.occ_cls = 'Industrial' THEN 1 ELSE 0 END) AS bldgs_industrial,
	sum(CASE WHEN buildings.occ_cls = 'Residential' THEN 1 ELSE 0 END) AS bldgs_residential,
	sum(CASE WHEN buildings.occ_cls = 'Utility and Misc' THEN 1 ELSE 0 END) AS bldgs_utility_msc,
	sum(CASE WHEN buildings.occ_cls = 'Other' THEN 1 WHEN buildings.occ_cls = 'Unclassified' THEN 1 WHEN buildings.occ_cls IS NULL THEN 1 ELSE 0 END) AS bldgs_other,
	to_char('1900-01-01 00:00:00'::timestamp without time zone, 'YYYY-MM-DD HH24:MI:SS UTC') AS reference_time,
	to_char(now()::timestamp without time zone, 'YYYY-MM-DD HH24:MI:SS UTC') AS update_time,
	counties.geom
INTO publish.ana_inundation_counties
FROM derived.counties AS counties
JOIN derived.channels_county_crosswalk AS crosswalk ON counties.geoid = crosswalk.geoid
JOIN publish.ana_inundation AS fim on crosswalk.feature_id = fim.feature_id
JOIN publish.ana_inundation_building_footprints AS buildings ON crosswalk.feature_id = buildings.feature_id
GROUP BY counties.geoid, counties.name, counties.geom, buildings.prop_st;

-------------- HUCS Summary ---------------
DROP TABLE IF EXISTS publish.ana_inundation_hucs;
SELECT
	hucs.huc10,
	TO_CHAR(hucs.huc10, 'fm0000000000') AS huc10_str,
	max(fim.streamflow_cfs) AS max_flow_cfs,
	avg(fim.streamflow_cfs) AS avg_flow_cfs,
	max(fim.fim_stage_ft) AS max_fim_stage_ft,
	avg(fim.fim_stage_ft) AS avg_fim_stage_ft,
	count(buildings.build_id) AS buildings_impacted,
	sum(buildings.sqfeet) AS building_sqft_impacted,
	sum(CASE WHEN buildings.occ_cls = 'Agriculture' THEN 1 ELSE 0 END) AS bldgs_agriculture,
	sum(CASE WHEN buildings.occ_cls = 'Assembly' THEN 1 ELSE 0 END) AS bldgs_assembly,
	sum(CASE WHEN buildings.occ_cls = 'Commercial' THEN 1 ELSE 0 END) AS bldgs_commercial,
	sum(CASE WHEN buildings.occ_cls = 'Education' THEN 1 ELSE 0 END) AS bldgs_education,
	sum(CASE WHEN buildings.occ_cls = 'Government' THEN 1 ELSE 0 END) AS bldgs_government,
	sum(CASE WHEN buildings.occ_cls = 'Industrial' THEN 1 ELSE 0 END) AS bldgs_industrial,
	sum(CASE WHEN buildings.occ_cls = 'Residential' THEN 1 ELSE 0 END) AS bldgs_residential,
	sum(CASE WHEN buildings.occ_cls = 'Utility and Misc' THEN 1 ELSE 0 END) AS bldgs_utility_msc,
	sum(CASE WHEN buildings.occ_cls = 'Other' THEN 1 WHEN buildings.occ_cls = 'Unclassified' THEN 1 WHEN buildings.occ_cls IS NULL THEN 1 ELSE 0 END) AS bldgs_other,
	to_char('1900-01-01 00:00:00'::timestamp without time zone, 'YYYY-MM-DD HH24:MI:SS UTC') AS reference_time,
	to_char(now()::timestamp without time zone, 'YYYY-MM-DD HH24:MI:SS UTC') AS update_time,
	hucs.geom
INTO publish.ana_inundation_hucs
FROM derived.huc10s_conus AS hucs
JOIN derived.featureid_huc_crosswalk AS crosswalk ON hucs.huc10 = crosswalk.huc10
JOIN publish.ana_inundation AS fim on crosswalk.feature_id = fim.feature_id
JOIN publish.ana_inundation_building_footprints AS buildings ON crosswalk.feature_id = buildings.feature_id
GROUP BY hucs.huc10, hucs.geom;

--------------- Critical Infrastructure Points ---------------
DROP TABLE IF EXISTS publish.ana_inundation_critical_infrastructure;
CREATE INDEX IF NOT EXISTS idx_critpoints_geom ON derived.static_public_critical_infrastructure_points_fema USING GIST(geometry);
ANALYZE derived.static_public_critical_infrastructure_points_fema;
CREATE INDEX IF NOT EXISTS idx_fim_geo_geom ON fim_ingest.ana_inundation_geo USING GIST(geom);
ANALYZE fim_ingest.ana_inundation_geo;
SELECT
	critpoints.build_type,
	critpoints.name,
	critpoints.geometry as geom,
	critpoints.city,
	critpoints.country,
	critpoints.state,
	critpoints.population,
	critpoints.beds,
	critpoints.naics_code,
	critpoints.specialty,
	critpoints.sourcedate,
	critpoints.zipcode,
	critpoints.status,
	critpoints.trauma,
	critpoints.alias,
	critpoints.county,
	critpoints.naics_desc,
	critpoints.alt_name,
	critpoints.naicsdescr,
	critpoints.helipad,
	critpoints.level_,
	critpoints.source,
	critpoints.type,
	flows.hydro_id,
	flows.hydro_id::TEXT AS hydro_id_str,
	flows.feature_id,
	flows.feature_id::TEXT AS feature_id_str,
	flows.discharge_cfs AS streamflow_cfs,
	fim.rc_stage_ft AS fim_stage_ft
INTO publish.ana_inundation_critical_infrastructure
FROM derived.static_public_critical_infrastructure_points_fema as critpoints
JOIN fim_ingest.ana_inundation_geo fim_geo ON ST_INTERSECTS(fim_geo.geom, critpoints.geometry)
JOIN fim_ingest.ana_inundation_flows flows ON fim_geo.hand_id = flows.hand_id
JOIN fim_ingest.ana_inundation fim ON fim_geo.hand_id = fim.hand_id;