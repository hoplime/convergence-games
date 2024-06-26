# This Dockerfile is intended for production deployment - local development should be done outside of Docker

ARG BUILD_BASE_IMAGE=python:3.12
ARG BASE_IMAGE=python:3.12

# BUILDER IMAGE
FROM ${BUILD_BASE_IMAGE} AS builder
WORKDIR /app_build

# Install poetry and npm
ENV PATH="/root/.local/bin:$PATH"
RUN apt-get update && \
    apt-get install --no-install-recommends --no-install-suggests -y curl npm software-properties-common && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.in-project true && \
    npm install npm@latest -g && \
    npm install n -g && \
    n lts

# Install application specific poetry dependencies
COPY pyproject.toml poetry.lock /app_build/
RUN poetry install --no-root --only main

# Install NPM packages
COPY package.json package-lock.json /app_build/
RUN npm install
COPY . /app_build/
RUN npm run tailwind:compile

# APPLICATION IMAGE
FROM ${BASE_IMAGE}
WORKDIR /app

# Copy the application code
COPY . /app/

# Copy the virtual environment and styles from the builder image
COPY --from=builder /app_build/.venv /app/.venv
COPY --from=builder /app_build/convergence_games/app/static/css/style.css /app/convergence_games/app/static/css/style.css

# Set the environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

CMD ["python", "-m", "uvicorn", "--host=0.0.0.0", "--port=8000", "convergence_games.app:app"]
