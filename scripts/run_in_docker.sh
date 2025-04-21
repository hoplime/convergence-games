#!/bin/bash
docker buildx bake && \
docker run --rm -it -p 8000:8000 --env-file=.env --env DATABASE_HOST=host.docker.internal jcheatley/waikato-rpg-convergence-games:latest