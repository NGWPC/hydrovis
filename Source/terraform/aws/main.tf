provider "aws" {
  region = var.region
}

resource "aws_iam_role" "rnr_instance_role" {
  name = "${var.env}_rnr_instance_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "rnr_s3_access_policy" {
  name = "${var.env}_rnr_s3_access_policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "s3:ListBucket"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:s3:::${var.rnr_s3_bucket}"
      },
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:s3:::${var.rnr_s3_bucket}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rnr_attach_s3_policy" {
  role       = aws_iam_role.rnr_instance_role.name
  policy_arn = aws_iam_policy.rnr_s3_access_policy.arn
}

resource "aws_iam_role_policy_attachment" "attach_extra_policy" {
  count      = var.extra_policy_arn != "" ? 1 : 0
  role       = aws_iam_role.rnr_instance_role.name
  policy_arn = var.extra_policy_arn
}

resource "aws_iam_instance_profile" "rnr_instance_profile" {
  name = "${var.env}_rnr_instance_profile"
  role = aws_iam_role.rnr_instance_role.name
}

resource "aws_security_group" "rnr_server_sg" {
  name_prefix = "rnr_server_sg"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "replace_n_route" {
  ami                  = var.rocky_linux_ami_id
  instance_type        = var.instance_type
  security_groups      = [aws_security_group.rnr_server_sg.id]
  subnet_id            = var.subnet_id
  iam_instance_profile = aws_iam_instance_profile.rnr_instance_profile.name

  root_block_device {
    volume_size = var.ebs_volume_size
    encrypted   = true
  }

  user_data = <<-EOF
              #!/bin/bash
              set -e

              # Install and start AWS SSM agent
              dnf install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
              systemctl enable amazon-ssm-agent
              systemctl start amazon-ssm-agent

              # Update system packages
              dnf upgrade -y
              dnf update -y
              dnf install -y git unzip

              # Install AWS CLI v2
              curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
              unzip -q awscliv2.zip
              ./aws/install --update

              # Verify AWS CLI installation
              aws --version

              # Install Docker
              dnf config-manager -y --add-repo=https://download.docker.com/linux/centos/docker-ce.repo
              dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

              systemctl start docker
              systemctl enable docker
              #usermod -aG docker ssm-user

              # Verify installation
              docker compose version

              # Set up the application directory
              mkdir -p /app
              chmod -R 777 /app
              cd /app

              # Clone the specified Git repository and branch
              git clone -b ${var.git_branch} ${var.git_repo_url} hydrovis

              # Ensure the required data directories are created
              mkdir /app/hydrovis/Source/data/output
              mkdir /app/hydrovis/Source/data/warehouse

              # Sync Hydrofabric Geo Package data from S3
              aws s3 sync s3://${var.rnr_s3_bucket}/${rfc_geopackage_data} /app/hydrovis/Source/data/parquet

              # Create and enable the docker compose script systemd service for future reboots
              cat <<-SERVICE_EOF > /etc/systemd/system/rnr-containers.service
              [Unit]
              Description=Docker Compose Application
              After=network.target

              [Service]
              Type=simple
              RemainAfterExit=true
              ExecStart=./start.sh
              ExecStop=./stop.sh
              WorkingDirectory=/app/hydrovis/Source/docker
              Restart=always

              [Install]
              WantedBy=multi-user.target
              SERVICE_EOF

              # Create and enable the docker compose script systemd service for future reboots
              cat <<-SERVICE_EOF > /etc/systemd/system/rnr-app.service
              [Unit]
              Description=The T-Route container commands to run in the background
              After=network.target

              [Service]
              Type=simple
              RemainAfterExit=true
              ExecStart=./run_rnr.sh
              WorkingDirectory=/app/hydrovis/Source/docker

              [Install]
              WantedBy=multi-user.target
              SERVICE_EOF

              # Reload systemd and enable the service
              systemctl daemon-reload
              systemctl enable rnr-containers
              systemctl start rnr-containers
              systemctl enable rnr-app
              systemctl start rnr-app

              # Set up the cron job
              (crontab -l 2>/dev/null || echo "") | \
                (echo "*/5 * * * * ./app/hydrovis/Source/docker/run_ingest.sh && ./app/hydrovis/Source/docker/run_post_process.sh && /usr/local/bin/aws s3 sync /app/hydrovis/Source/RnR/data/output/*.csv s3://${var.rnr_s3_bucket}/replace_and_route/") | crontab -

              # Check the crontab
              crontab -l
              EOF

  tags = {
    Name = "${var.env}-ReplaceNRoute-Instance"
  }
}
