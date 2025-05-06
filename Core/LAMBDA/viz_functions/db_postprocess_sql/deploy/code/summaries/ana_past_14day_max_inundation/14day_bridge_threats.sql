-- Ultimately, we want a unique bridge point (osmid) and the feature id
-- tied to it that has the highest risk_status_code and highest threshold_discharge_cfs

DROP TABLE IF EXISTS publish.ana_past_14day_max_inundation_bridge_threats;

-- At this point, we can have dup osmid, but each tied to a different feature
-- and each record will calc a risk code based on if the source feature discharge:
-- if the source feature discharge has a higher discharge then the bp.threshold_discharge_cfs, then code 2
-- if the source feature discharge has a lower than bp.threshold_discharge_cfs but higher than
-- the bp.threshold_discharge_75_cfs (75% of the max bp.threshold_discharge_cfs), then the code is 1
-- if it is lower than threshold_discharge_75_cfs, then the code is 0.
-- Note.. we do the IS NULL test against bp.threshold_discharge_cfs as not all
-- features will have matching bridges and visa-versa
SELECT
    bp.osmid,
    bp.name,
    bp.feature_id,
    bp.threshold_hand_ft,
    bp.threshold_hand_75_ft,
    bp.threshold_discharge_cfs,
    bp.threshold_discharge_75_cfs,
 	flows.feature_id as src_feature_id,
 	flows.discharge_cfs as src_flow_dis,
    CASE
		WHEN bp.threshold_discharge_cfs IS NULL THEN -1
        WHEN flows.discharge_cfs < bp.threshold_discharge_cfs AND
		     flows.discharge_cfs >= bp.threshold_discharge_75_cfs THEN 1
        WHEN flows.discharge_cfs >= bp.threshold_discharge_cfs THEN 2
        ELSE 0
        END AS risk_status_code,
    bp.oid,	
	bp.is_backwater,
    bp.has_lidar_tif,
    bp.hydroid,
    bp.branch,
    bp.mainstem,
    bp.bridge_type,
    bp.huc8,
    bp.geom
INTO TEMP TABLE tt_w_risk_codes
FROM cache.max_flows_ana_14day AS flows
JOIN derived.bridge_points AS bp
ON flows.feature_id = bp.feature_id; 

-- For any rec that has a dup osmid, we want the osmid with the highest code
-- This might also result in dup osmids.
SELECT rc.*
INTO TEMP TABLE tt_osm_max_code
FROM (
	select osmid,
	max (risk_status_code) as max_code
	from tt_w_risk_codes
	group by osmid
) s JOIN tt_w_risk_codes rc
ON s.osmid = rc.osmid AND s.max_code = rc.risk_status_code;

-- now we can filter down to one osmid (bridge point) based which bridge point
-- had the highest bp.threshold_discharge_cfs. In theory, should be no dups
-- but leave it if that super rare occurence happens
select mc.*
INTO publish.ana_past_14day_max_inundation_bridge_threats
FROM (
	select osmid, 
	max ( threshold_discharge_cfs) as max_dis
	from tt_osm_max_code
	group by osmid
) s JOIN tt_osm_max_code mc
    ON s.osmid = mc.osmid
   AND s.max_dis = mc.threshold_discharge_cfs; 

-- Drop the oid column? Only when in a production model and what is checked into git
-- Why? the publish schema gets copied over to a service schema which add a new oid
-- back in.
-- When dev testing against a local arcpro, dont' drop the column
ALTER TABLE publish.ana_past_14day_max_inundation_bridge_threats;
DROP COLUMN oid;
