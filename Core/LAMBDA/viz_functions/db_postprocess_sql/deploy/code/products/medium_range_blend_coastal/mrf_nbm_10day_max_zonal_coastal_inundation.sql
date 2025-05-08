DROP TABLE IF EXISTS publish.mrf_nbm_10day_max_zonal_coastal_inundation_atlgulf;

SELECT
    coastal_inundation.geom, 
    coastal_inundation.reference_time,
    to_char(now()::timestamp without time zone, 'YYYY-MM-DD HH24:MI:SS UTC') AS update_time, 
    coastal_inundation.reference_time AS valid_time
INTO publish.mrf_nbm_10day_max_zonal_coastal_inundation_atlgulf
FROM ingest.mrf_nbm_10day_max_zonal_coastal_inundation_atlgulf coastal_inundation;