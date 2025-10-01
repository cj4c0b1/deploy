#!/bin/sh
# wait-for-mqtt.sh

set -e

host="$1"
shift
port="$1"
shift
cmd="$@"

# Install wget if not available
if ! command -v wget > /dev/null; then
    apk add --no-cache wget
fi

# Try to connect to the MQTT port using wget
until wget --timeout=1 -q --spider $host:$port; do
  >&2 echo "MQTT broker is unavailable - sleeping"
  sleep 1
done

>&2 echo "MQTT broker is up - executing command"
exec $cmd
