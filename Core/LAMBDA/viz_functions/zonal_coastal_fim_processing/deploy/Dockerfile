# Use AWS Lambda Python 3.9 base image
FROM public.ecr.aws/lambda/python:3.9

# Install Miniconda and required system tools
RUN yum install -y wget bzip2 && \
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh

# Add conda to the PATH
ENV PATH="/opt/conda/bin:${PATH}"   

# Install Development Tools and cmake3
RUN yum groupinstall "Development Tools" -y && \
    yum install -y cmake3 && \
    ln -s /usr/bin/cmake3 /usr/bin/cmake

# Set working directory in the container
WORKDIR /app

# Copy code directory into the container
COPY code /app/code

# Install dependencies via conda-linux-64.lock
COPY conda-linux-64.lock /app/conda-linux-64.lock
RUN conda create --name coastal_fim_vis --file /app/conda-linux-64.lock

# Install DuckDB and some troublesome dependencies not working in the lock file (investigate later)
RUN /opt/conda/bin/conda run -n coastal_fim_vis pip install duckdb==1.1.3 s3fs awslambdaric

# Install DuckDB spatial extension into the environment
RUN /opt/conda/bin/conda run -n coastal_fim_vis python -c "import duckdb; duckdb.sql('INSTALL spatial'); duckdb.sql('LOAD spatial')"

# Set default environment to the one created for subsequent RUN commands
SHELL ["conda", "run", "-n", "coastal_fim_vis", "/bin/bash", "-c"]

# Set working directory for Lambda runtime
WORKDIR /var/task

# Copy all code into /var/task
COPY code/ /var/task/

# Copy bootstrap.sh
COPY bootstrap.sh /var/task/bootstrap.sh
RUN chmod +x /var/task/bootstrap.sh

# Set the ENTRYPOINT to the bootstrap script and the CMD to specify handler.
ENTRYPOINT ["/var/task/bootstrap.sh"]
CMD ["lambda_function.lambda_handler"]
