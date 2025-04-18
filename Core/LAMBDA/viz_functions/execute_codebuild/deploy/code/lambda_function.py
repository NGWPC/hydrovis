import time
import boto3

client = boto3.client('codebuild')

def lambda_handler(event, context):
    project_name = event['project_name']
    response = client.start_build(projectName=project_name)
    build_id = response["build"]["id"]

    max_wait = 600  # 10 minutes
    total_wait = 0
    iter_sleep = 10

    while total_wait < max_wait:
        response = client.batch_get_builds(ids=[build_id])
        build_status = response["builds"][0]["buildStatus"]
        if build_status == "SUCCEEDED":
            break
        elif build_status == "FAILED":
            raise Exception(f"Failed to build {project_name}")
        time.sleep(iter_sleep)
        total_wait += 10

    if total_wait >= max_wait:
        raise Exception("Failed to build {project_name} within configured max_wait of {max_wait} seconds")

    print(f"Successfully built {project_name}")
