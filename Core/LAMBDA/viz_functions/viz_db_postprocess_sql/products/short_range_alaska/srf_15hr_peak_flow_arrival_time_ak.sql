DROP TABLE IF EXISTS publish.srf_15hr_peak_flow_arrival_time_alaska;

SELECT
    forecasts.feature_id,
    forecasts.feature_id::TEXT AS feature_id_str,
    channels.name,
    channels.strm_order::integer,
    channels.huc6,
    'AK' AS state,
    forecasts.nwm_vers,
    forecasts.reference_time,
    CASE WHEN rf.high_water_threshold = -9999 THEN NULL ELSE min(forecast_hour) END AS peak_flow_arrival_hour,
    CASE WHEN rf.high_water_threshold = -9999 THEN NULL ELSE to_char(forecasts.reference_time::timestamp without time zone + INTERVAL '1 hour' * min(forecast_hour), 'YYYY-MM-DD HH24:MI:SS UTC') END AS peak_flow_arrival_time,
    CASE WHEN rf.high_water_threshold = -9999 THEN NULL ELSE arrival_time.below_bank_return_hour END AS below_bank_return_hour,
    CASE WHEN rf.high_water_threshold = -9999 THEN NULL ELSE arrival_time.below_bank_return_time END AS below_bank_return_time,
    round(max_flows.discharge_cfs::numeric, 2) AS max_flow_cfs,
    rf.high_water_threshold,
    to_char(now()::timestamp without time zone, 'YYYY-MM-DD HH24:MI:SS UTC') AS update_time,
    channels.geom

INTO publish.srf_15hr_peak_flow_arrival_time_alaska
FROM ingest.nwm_channel_rt_srf_ak AS forecasts 

-- Join in max flows on max streamflow to only get peak flows
JOIN cache.max_flows_srf_ak AS max_flows
    ON forecasts.feature_id = max_flows.feature_id AND forecasts.streamflow = max_flows.discharge_cms

-- Join in channels data to get reach metadata and geometry
JOIN derived.channels_ak as channels ON forecasts.feature_id = channels.feature_id::bigint

-- Join in recurrence flows to get high water threshold
JOIN derived.recurrence_flows_ak AS rf ON forecasts.feature_id = rf.feature_id

-- Join in high water arrival time for return time (the yaml config file ensures that arrival time finishes first for this, but we'll join on reference_time as well to ensure)
JOIN publish.srf_15hr_high_water_arrival_time_alaska AS arrival_time ON forecasts.feature_id = arrival_time.feature_id and forecasts.reference_time = arrival_time.reference_time

WHERE round((forecasts.streamflow*35.315)::numeric, 2) >= rf.high_water_threshold
GROUP BY forecasts.feature_id, forecasts.reference_time, forecasts.nwm_vers, arrival_time.below_bank_return_hour, arrival_time.below_bank_return_time, max_flows.discharge_cfs, channels.geom, channels.strm_order, channels.name, channels.huc6, rf.high_water_threshold;