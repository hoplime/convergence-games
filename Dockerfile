FROM node:23-slim@sha256:dfb18d8011c0b3a112214a32e772d9c6752131ffee512e974e59367e46fcee52 AS node-builder

WORKDIR /app

COPY . /app

RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm install && npm run build

# Now we have outputs at
# /app/convergence_games/app/static/css/style.css
# /app/convergence_games/app/static/js/lib.js

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:5c8edeb8b5644b618882e06ddaa8ddf509dcd1aa7d08fedac7155106116a9a9e AS python-builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_INSTALL_DIR=/python
ENV UV_PYTHON_PREFERENCE=only-managed

RUN uv python install 3.12

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM debian:bookworm-slim@sha256:b1211f6d19afd012477bd34fdcabb6b663d680e0f4b0537da6e6b0fd057a3ec3 AS default

WORKDIR /app

# Install ca-certificates - so we can use https to get JWKs from Google etc
# Also install ssh dependencies - so we can use ssh to connect to the container in Azure
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        dialog \
        openssh-server \
        &&\
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean
COPY ssh_entrypoint/sshd_config /etc/ssh/
COPY ssh_entrypoint/entrypoint.sh ./entrypoint.sh
RUN chmod u+x ./entrypoint.sh

# Copy built files
COPY --from=python-builder /python /python
COPY --from=python-builder /app /app
COPY --from=node-builder /app/convergence_games/app/static/css/style.css /app/convergence_games/app/static/css/style.css
COPY --from=node-builder /app/convergence_games/app/static/js/lib.js /app/convergence_games/app/static/js/lib.js
COPY --from=node-builder /app/convergence_games/app/static/js/lib.js.map /app/convergence_games/app/static/js/lib.js.map

# Set up the environment
ENV PATH="/app/.venv/bin:$PATH"
ARG BUILD_TIME
ENV LAST_UPDATED=$BUILD_TIME

# Create the cache busted versions of style.css and lib.js
ENV USE_CACHE_BUSTED_FILES=1
RUN RELEASE=$(date -d "$LAST_UPDATED" +"%Y.%m.%d+%H.%M.%S") && \
    mv /app/convergence_games/app/static/css/style.css /app/convergence_games/app/static/css/style.$RELEASE.css && \
    mv /app/convergence_games/app/static/js/lib.js /app/convergence_games/app/static/js/lib.$RELEASE.js

CMD ["python", "-m", "uvicorn", "--host=0.0.0.0", "convergence_games.app:app"]

FROM default AS azure

EXPOSE 8000 2222
RUN echo "root:Docker!" | chpasswd

ENTRYPOINT [ "./entrypoint.sh" ]
CMD ["python", "-m", "uvicorn", "--host=0.0.0.0", "convergence_games.app:app"]

FROM default