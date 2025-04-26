#!/bin/bash

set -e
service ssh start
if [[ -z "$DEBUG_SERVER_CONFIG" ]]; then
    # We pass the command as CMD in the Dockerfile
    exec "$@"
else
    # We just run a simple HTTP server, not the one in the container
    # This is useful for debugging the container
    # and for testing the SSH connection
    exec python -m http.server
fi
