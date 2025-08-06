#!/bin/sh
#
# This script is the entrypoint for the Docker container.
# It starts the Docker daemon in the background and then executes
# the main application. This is necessary to support Docker-in-Docker
# functionality required by the MCP Anywhere's container manager.

set -e

# Start Docker daemon in the background
# The 'dockerd-entrypoint.sh' script is the default entrypoint for the dind image.
# We run it in the background to start the daemon.
# Logs will now go to the container's stdout/stderr and be captured by Fly.
dockerd-entrypoint.sh &

# Wait for the Docker socket to be available.
# We'll poll for a maximum of 20 seconds.
echo "Waiting for Docker daemon to start..."
counter=0
while [ ! -S /var/run/docker.sock ]; do
  if [ $counter -ge 20 ]; then
    echo "Docker daemon failed to start in 20 seconds."
    exit 1
  fi
  sleep 1
  counter=$((counter+1))
done
echo "Docker daemon started."

# Execute the command passed to the container (e.g., gunicorn)
exec "$@" 