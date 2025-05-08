FROM ghcr.io/mamba-org/micromamba:latest AS micromamba

# Create conda environment for hydrovis
RUN --mount=type=bind,source=conda-linux-64.lock,target=/tmp/conda.lock \
    micromamba install -y --file /tmp/conda.lock && \
    micromamba clean -afy

# Clean out unnecessary files to reduce image size
RUN find /opt/conda -regex '^.*\(__pycache__\|\.py[co]\)$' -delete && \
    find /opt/conda -follow -type f -name '*.a' -delete
RUN rm -rf /opt/conda/man /opt/conda/share/man /opt/conda/share/doc && \
    rm -rf /opt/conda/include && \
    rm -rf /opt/conda/share/bash-completion && \
    rm -rf /opt/conda/share/info && \
    rm -rf /opt/conda/share/examples && \
    rm -rf /opt/conda/conda-meta

FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal AS alinux

RUN dnf install -y awscli

##############################################################################
## Setup Flows2fim
##############################################################################
RUN mkdir -p /var/task
ARG AWS_DEFAULT_REGION
ARG AWS_CONTAINER_CREDENTIALS_RELATIVE_URI
RUN aws s3 cp s3://hv-vpp-dev-ripple/software/latest/linux-amd64/flows2fim /var/task/flows2fim

FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal AS final

ENV MAMBA_ROOT_PREFIX="/opt/conda"
ENV MAMBA_EXE="/bin/micromamba"
# Prevent Python from writing bytecode files
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent python from buffering stdout
ENV PYTHONUNBUFFERED=1
COPY --from=micromamba --chown=root "$MAMBA_EXE" "$MAMBA_EXE"
COPY --from=micromamba --chown=root /opt/conda /opt/conda
COPY --from=micromamba --chown=root /usr/local/bin/_*.sh /usr/local/bin/

WORKDIR /home/code
# Copy function code
COPY code/ ./

COPY --from=alinux --chmod=755 /var/task/flows2fim .
RUN mkdir -p /tmp/data/inputs
RUN mkdir -p /tmp/data/outputs
RUN mkdir -p /tmp/data/logs

SHELL ["/usr/local/bin/_dockerfile_shell.sh"]

ENTRYPOINT [ "/usr/local/bin/_entrypoint.sh" ]
CMD [ \
    "python", "-m", "awslambdaric", "lambda_function.lambda_handler" \
]

