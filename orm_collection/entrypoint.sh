#!/bin/sh
# All configuration is supplied by the environment the container is run
# with (docker-compose's `env_file:`, `docker run --env-file`, or the
# hosting platform's own secrets injection) -- nothing is baked into the
# image or read from a file inside it.
exec "$@"
