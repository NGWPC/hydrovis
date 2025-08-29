output "job_definition" {
  value = aws_batch_job_definition.schism_fim_job_definition
}

output "job_queue" {
  value = aws_batch_job_queue.schism_fim_job_queue
}

output "execution_role_arn" {
  value = aws_iam_role.schism_execution.arn
}