FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    CONDA_DIR=/opt/conda \
    PATH=/opt/conda/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        wget \
        ca-certificates \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
        tzdata \
        python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Mambaforge for faster dependency resolution
RUN wget -q https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh -O /tmp/mambaforge.sh && \
    bash /tmp/mambaforge.sh -b -p ${CONDA_DIR} && \
    rm /tmp/mambaforge.sh && \
    mamba clean -y --all

WORKDIR /workspace/Tri-ARC

# Copy environment manifests first to leverage Docker layer caching
COPY requirements.txt ./requirements.txt
COPY environments/conda/environment.yml ./environment.yml

RUN mamba env create -f environment.yml && \
    echo "conda activate tri-arc" >> /etc/profile.d/conda.sh

# Activate environment and install any remaining wheels (pre-baked under vendor/wheels)
COPY vendor ./vendor
RUN source ${CONDA_DIR}/etc/profile.d/conda.sh && \
    conda activate tri-arc && \
    if [ -d vendor/wheels ]; then \
        pip install --no-index --find-links vendor/wheels -r requirements.txt; \
    else \
        pip install -r requirements.txt; \
    fi && \
    conda clean -y --all && \
    rm -rf /root/.cache/pip

# Copy the rest of the project
COPY . .

ENTRYPOINT ["/bin/bash", "-lc"]
CMD ["conda activate tri-arc && python scripts/self_test.py"]
