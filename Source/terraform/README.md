# Replace and Route (RnR) Terraform Deployment

## Overview

This README provides a guide on deploying the Replace and Route (RnR) application and its dependencies on an AWS EC2 instance using Terraform. The deployment includes setting up IAM roles, security groups, and an EC2 instance with the necessary software, Docker containers, a systemd service called rnr-app that will run the applications via docker compose, and a cron job for scheduled execution of the data publisher.

The configurations supports AWS and is meant to be extendable to optionally support deployment to Azure and GCP in the future.

Only the AWS code has been run in NGWPC dev environments, and multiple considerations are left for the deployer at this early stage around providing an appropriate config with regard to database and network access.  It is very likely that the future iterations of any deployment for RnR and T-route will look different from this MVP

## Prerequisites

- [Terraform](https://www.terraform.io/downloads.html) installed.
- Appropriate, configured cloud provider credentials. This does interact with IAM, so it requires Admin level privileges.
- An existing VPC and subnet in the AWS region you plan to deploy.
- Available Rocky 9 AMI. A similar RHEL or CentOS based AMI should work with minor changes to the user_data. An Ubuntu based AMI would require more with a change to APT based package management.
- S3 Bucket containing the required Hydrofabric parquet data and the database config file.

## Base Configuration and Deploy

### S3 Bucket & Contents

#### Hydrofabric Geo Package data
For the application to run, appropriate Hydrofabric parquet data must be provided in a specified location in the target S3 bucket.

s3://${var.rnr_s3_bucket}/${var.rfc_geopackage_data}/

Currently we expect var.rfc_geopackage_data to be either "pi_6/" since this data was created in PI6, but the variable isn't restricted to set values and should be set appropriately for your given environment.


### Configuration (variables)

To streamline the deployment process and avoid being prompted for every variable, you can create a terraform.tfvars file to predefine values for the target-specific variables in your Terraform configuration. This file allows you to set values for variables such as region, vpc_id, subnet_id, instance_type, rocky_linux_ami_id, git_repo_url, git_branch, rnr_s3_bucket, and rfc_geopackage_data. By populating the terraform.tfvars file with these values, Terraform will automatically use them during the deployment, ensuring consistency across environments and eliminating the need for manual input.

Simply create the terraform.tfvars file in the root directory of your Terraform project, and add entries like region = "us-west-2", vpc_id = "vpc-xxxxxx", etc., corresponding to the variables you want to set. A common practice in Terraform to manage different configurations for various environments such as development, staging, and production is to create multiple tfvars files and target them per environment. For each environment, create a separate .tfvars file. For example:

- dev.tfvars
- staging.tfvars
- oe.tfvars

Each of these files would contain the variables specific to that environment, and when deploying, you can target the specific environment variable file by leveraging the -var-file flag.

### Cloud Service Provider Terraform Configuration and Deploy

We've only been working with AWS thus far, so we'll focus on that configuration.

## Usage

### AWS

1. Navigate to the appropriate Cloud Service Provider directory:

    There are a lot of questions that need to be answered around targettin existing OWP internal resources (RDBMS & Object Storage: S3) if deploying to a Cloud Service Provider other than AWS.  Docker Compose based deploys are technically compatible with any host of sufficient size running an appropriate version of Docker with the Docker Compose plugin, but the deployed applications still needthe same access to pre-requisite services in OWPs existing environment or equivalent copies need to be created in the target CSP.

    ```sh
    # Currently supported
    cd aws

    # Potential Future Targets
    cd gcp
    cd azure
    ```

2. Update or create a variables.tfvars file with values appropriate for your targeted deployment as described in the generic configuration instructions.

    See below for an explanation of each variables listed.

    env = "test":
    - Purpose: Specifies the environment for which this configuration is intended.
    - Details: In this case, the environment is labeled as "test", which might be used to distinguish it from other environments like "dev", "staging", or "oe". This variable can be used in naming conventions for resources that are created to ensure they are environment-specific.

    region = "us-east-1":
    - Purpose: Defines the AWS region where the resources will be deployed.
    - Details: us-east-1 corresponds to the N. Virginia region, one of the most commonly used regions due to its extensive AWS services availability.

    vpc_id = "vpc-xxxxxxxxxxxxxxx":
    - Purpose: Specifies the ID of the Virtual Private Cloud (VPC) where the resources will be created.
    - Details: This VPC is a logically isolated section of the AWS cloud where you can launch AWS resources in a virtual network that you define.

    subnet_id = "subnet-xxxxxxxxxxxxxx":
    - Purpose: Identifies the specific subnet within the VPC where the EC2 instance will be launched.
    - Details: Subnets are segments of a VPC’s IP address range where resources are placed. This subnet should be associated with an availability zone within the specified region.

    instance_type = "c5.xlarge":
    - Purpose: Determines the type of EC2 instance to launch.
    - Details: c5.xlarge is a compute-optimized instance type, providing a good balance of compute power and memory for applications that require high performance, such as Replace and Route.

    ebs_volume_size = 100:
    - Purpose: Specifies the size (in GB) of the Elastic Block Store (EBS) volume attached to the instance.
    - Details: This storage volume is used for data persistence. A 100 GB volume should be sufficient for testing purposes, depending on the application’s data requirements.

    rnr_s3_bucket = "ngwpc-rnr-test":
    - Purpose: Defines the name of the S3 bucket where the application will store and retrieve data. In particular, the code sources required Hydrofabric Geo Package data version 20.1 from this bucket and database connection config details. This terraform creates a role with appropriate access granted to the bucket name provided here. Note that this will only work if the bucket is in the same account as your deployment. Modifications will need to be made to support multi-account architectures.
    - Details: This S3 bucket is specific to the test environment and is used by Replace and Route to manage files and configurations.

    rfc_geopackage_data = "replace-and-route/rfc-geopackages/" or "rnr_shortest_paths/"
    - Purpose: Definines the location of the rfc geaopackage data one specifically wants to use when running RnR.
    - Details: Originally this always pointed at "replace-and-route/rfc-geopackages/", but a variable was added to support future functionality leveraging "rnr_shortest_paths/".

    extra_policy_arn = "arn:aws:iam::xxxxxxxxx:policy/AWSAccelerator-SessionManagerLogging":
    - Purpose: Adds an additional IAM policy to the instance role.
    - Details: (Optional) This specific policy is necessary for enabling AWS Systems Manager (SSM) session manager logging in the NGWPC environments, allowing for secure remote access and session logging.  You could use this to attach any policy required in your account in addition to the one created by this terraform for S3 access. If you leave this variable out of your config or blank, nothing will be added.

    git_repo_url = "https://github.com/NGWPC/hydrovis.git"
    - Purpose: Indicates the Git Repo that should be used when cloning the application repository.
    - Details: (Optional) This value defaults to: https://github.com/NGWPC/hydrovis.git, but you might need to change it should you be running this from a Fork of that repo or if this repo has been merged or moved in your environment.

    git_branch = "pi_6":
    - Purpose: Indicates which Git branch should be used when cloning the application repository.
    - Details: The "pi_6" branch is likely where active development and testing occur for this current deliverable, making it suitable for the test environment, while main or a specific tag would be more appropriate for a production or production like environment.

    rocky_linux_ami_id = "ami-09fb459fad4613d55":
    - Purpose: Specifies the Amazon Machine Image (AMI) ID used to launch the EC2 instance.
    - Details: This AMI ID corresponds to a Rocky 9 Linux image. This specific ID points to a version that’s appropriate for the region us-east-1, but you must subscribe to the official Rocky AMIs. They do not currently charge any fee on top of your EC2 costs.


3. Initialize Terraform:
    ```sh
    terraform init
    ```
4. Review the Terraform plan (targetting your specific tfvars file):
    ```sh
    terraform plan -var-file=test.tfvars
    ```

4. Apply the Terraform configuration (targetting your specific tfvars file):
    ```sh
    terraform apply -var-file=test.tfvars
    ```

### Azure
Modify the variables.tf file to specify the appropriate values for your environment, such as location, resource_group_name, vm_size, subnet_id
### GCP
Modify the variables.tf file to specify the appropriate values for your environment, such as project, region, zone, vm_name, vm_machine_type, subnetwork, network, image_project, image_family

## Cleaning Up
To destroy the resources created by Terraform, navigate to the respective directory and run:

```sh
terraform destroy
```

### Notes
Ensure that you have the necessary IAM permissions to create and manage resources in your cloud environment.
The cron job setup is a prototype and should be adjusted as per your specific requirements.
This configuration does not assign a public IP to the VMs. Access should be managed through a VPN or bastion host.

## AWS Terraform Walkthrough

This serves as a brief walkthrough of the fairly simple provided Terraform solution. Ideally, this is enough information to help with any changes or customizations required to deploy to your environment.

### Provider Configuration:
The Terraform AWS provider is configured with the region specified in the variable var.region.

### IAM Role and Instance Profile
The IAM role is assigned to the EC2 instance, allowing it to interact with AWS services like S3. The following resources are created:
- IAM Role: Grants the EC2 instance permission to assume the role.
- IAM Policy: Grants S3 access for syncing application data.
- Instance Profile: Associates the IAM role with the EC2 instance.

### Security Group
A security group is created to allow SSH access and open the necessary ports for the application and services.  Specific required ports are still TBD as this is meant to run without intervention or any interface.

### EC2 Instance
The EC2 instance is configured via the instance user_date with necessary software including Docker, Docker Compose and the AWS CLI. It will automatically clone the RnR application code, sync data from S3, and start the services defined in the Docker Compose configuration via a systemd service called rnr-app.

Example of checking the status via systemd. The app(s) can be stopped and started similarly via systemctl stop and start.

*Note:* If you would like to see the files that are being generated from RnR, go to the `/app/hydrovis/Source/data/output` directory on the EC2. `/app/hydrovis/Source` is the location for all RnR code delivered as IaC
