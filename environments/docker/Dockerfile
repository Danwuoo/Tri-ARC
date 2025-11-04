FROM nvidia/cuda:12.1.1-cudnn9-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/tri-arc/.venv \
    PATH="/opt/tri-arc/.venv/bin:${PATH}"

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
      bash \
      build-essential \
      ca-certificates \
      curl \
      git \
      python3.11 \
      python3.11-venv \
      python3-pip \
      wget \
      unzip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/tri-arc
COPY requirements.txt requirements.txt

RUN python3.11 -m venv "${VIRTUAL_ENV}" && \
    "${VIRTUAL_ENV}/bin/pip" install --upgrade pip && \
    "${VIRTUAL_ENV}/bin/pip" install --extra-index-url https://download.pytorch.org/whl/cu121 -r requirements.txt

COPY . .

CMD ["python", "-m", "scripts.self_test", "--output", "reports/setup_verification_docker.md"]
