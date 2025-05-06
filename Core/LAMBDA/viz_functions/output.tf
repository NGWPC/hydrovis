output "db_ingest" {
  value = length(module.db-ingest) == 1 ? module.db-ingest[0].lambda : null
}

output "db_postprocess_sql" {
  value = length(module.db-postprocess-sql) == 1 ? module.db-postprocess-sql[0].lambda : null
}

output "egis_health_checker" {
  value = length(module.egis-health-checker) == 1 ? module.egis-health-checker[0].lambda : null
}

output "fim_data_prep" {
  value = length(module.fim-data-prep) == 1 ? module.fim-data-prep[0].lambda : null
}

output "hand_fim_processing" {
  value = length(module.hand-fim-processing) == 1 ? module.hand-fim-processing[0].lambda : null
}

output "initialize_pipeline" {
  value = length(module.initialize-pipeline) == 1 ? module.initialize-pipeline[0].lambda : null
}

output "optimize_rasters" {
  value = length(module.optimize-rasters) == 1 ? module.optimize-rasters[0].lambda : null
}

output "publish_service" {
  value = length(module.publish-service) == 1 ? module.publish-service[0].lambda : null
}

output "python_preprocessing" {
  value = length(module.python-preprocessing) == 1 ? module.python-preprocessing[0].lambda : null
}

output "python_preprocessing_3GB" {
  value = length(module.python-preprocessing) == 1 ? module.python-preprocessing[0].lambda : null
}

output "python_preprocessing_10GB" {
  value = length(module.python-preprocessing) == 1 ? module.python-preprocessing[0].lambda : null
}

output "raster_processing" {
  value = length(module.raster-processing) == 1 ? length(module.raster-processing) == 1 ? module.raster-processing[0].lambda : null : null
}

output "schism_fim" {
  value = length(module.schism-fim) == 1 ? module.schism-fim[0]: null
}

output "test_wrds_db" {
  value = length(module.test-wrds-db) == 1 ? module.test-wrds-db[0].lambda : null
}

output "update_egis_data" {
  value = length(module.update-egis-data) == 1 ? module.update-egis-data[0].lambda : null
}

output "zonal_coastal_fim_processing" {
  value = length(module.zonal-coastal-fim-processing) == 1 ? module.zonal-coastal-fim-processing[0].lambda : null
}

output "egis_healthcheck_alarm" {
  value = aws_cloudwatch_metric_alarm.egis_healthcheck_errors
}