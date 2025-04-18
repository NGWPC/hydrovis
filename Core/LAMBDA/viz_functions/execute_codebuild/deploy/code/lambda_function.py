import json
import os
import subprocess
import time

def lambda_handler(event, context):
    project_name = event['project_name']

    result = subprocess.run(["aws", "codebuild", "start-build", "--project-name", project_name], capture_output=True, text=True)
    output = result.stdout
    json_output = json.loads(output)
    build_id = json_output["build"]["id"]

    max_wait = 300  # 5 minutes
    total_wait = 0
    iter_sleep = 10

    while total_wait < max_wait:
        result = subprocess.run(["aws", "codebuild", "batch-get-builds", "--ids", build_id], capture_output=True, text=True)
        output = result.stdout
        json_output = json.loads(output)
        build_status = json_output["builds"][0]["buildStatus"]
        if build_status == "SUCCEEDED":
            break
        elif build_status == "FAILED":
            raise Exception(f"Failed to build {project_name}")
        time.sleep(iter_sleep)
        total_wait += 10

    if total_wait >= max_wait:
        raise Exception("Failed to build {PROJECT_NAME} within configured max_wait of {max_wait} seconds")

    print(f"Successfully built {project_name}")
