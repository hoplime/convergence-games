#!/bin/bash
set -e
service ssh start
# We pass the command as CMD in the Dockerfile
exec "$@"