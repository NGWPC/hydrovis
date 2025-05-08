FROM mambaorg/micromamba AS micromamba

# Create conda environment for hydrovis
RUN --mount=type=bind,source=conda-linux-64.lock,target=/tmp/conda.lock \
    micromamba install -y --file /tmp/conda.lock && \
    micromamba clean -afy

RUN find /opt/conda -regex '^.*\(__pycache__\|\.py[co]\)$' -delete && \
    find /opt/conda -follow -type f -name '*.a' -delete
RUN rm -rf /opt/conda/man /opt/conda/share/man /opt/conda/share/doc && \
    rm -rf /opt/conda/include && \
    rm -rf /opt/conda/share/bash-completion && \
    rm -rf /opt/conda/share/info && \
    rm -rf /opt/conda/share/examples && \
    rm -rf /opt/conda/conda-meta

USER root
# Install curl and gzip
RUN apt-get update && \
    apt-get install -y curl gzip && \
    rm -rf /var/lib/apt/lists/*

# Installing duckdb spatial extension    
RUN mkdir -p /opt/duckdb_extensions && \
    curl http://extensions.duckdb.org/v1.2.2/linux_amd64/spatial.duckdb_extension.gz \
      -o /opt/duckdb_extensions/spatial.duckdb_extension.gz && \
    gzip -d /opt/duckdb_extensions/spatial.duckdb_extension.gz

FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal AS alinux

ENV MAMBA_ROOT_PREFIX="/opt/conda"
ENV MAMBA_EXE="/bin/micromamba"
# Prevent Python from writing bytecode files
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent python from buffering stdout
ENV PYTHONUNBUFFERED=1

# Copy micromamba environment
COPY --from=micromamba --chown=root "$MAMBA_EXE" "$MAMBA_EXE"
COPY --from=micromamba --chown=root /opt/conda /opt/conda
COPY --from=micromamba --chown=root /usr/local/bin/_*.sh /usr/local/bin/
COPY --from=micromamba --chown=root /opt/duckdb_extensions /opt/duckdb_extensions
ENV DUCKDB_SPATIAL_EXTENSION_PATH="/opt/duckdb_extensions/spatial.duckdb_extension"

WORKDIR /home/code

# Copy function code
COPY code/ ./

SHELL ["/usr/local/bin/_dockerfile_shell.sh"]

ENTRYPOINT [ "/usr/local/bin/_entrypoint.sh" ]

CMD [ \
    "python", "-m", "awslambdaric", "lambda_function.lambda_handler" \
]