#!/bin/sh
set -eu
set +x

DYNSEC_CONFIG=/mosquitto/data/dynamic-security.json
MOSQUITTO_UID=1883
MOSQUITTO_GID=1883

mkdir -p /mosquitto/data
chown "$MOSQUITTO_UID:$MOSQUITTO_GID" /mosquitto/data
chmod 0700 /mosquitto/data

if [ ! -f "$DYNSEC_CONFIG" ]; then
    admin_username=${DEVICEOPS_DYNSEC_ADMIN_USERNAME:-deviceops-dynsec-admin}

    if [ -z "${DEVICEOPS_DYNSEC_ADMIN_PASSWORD:-}" ]; then
        echo "ERROR: DEVICEOPS_DYNSEC_ADMIN_PASSWORD is required to initialize Dynamic Security." >&2
        exit 1
    fi

    if [ -z "$admin_username" ]; then
        echo "ERROR: DEVICEOPS_DYNSEC_ADMIN_USERNAME must not be empty." >&2
        exit 1
    fi

    temp_config="${DYNSEC_CONFIG}.tmp.$$"
    trap 'rm -f "$temp_config"' EXIT HUP INT TERM

    echo "Initializing the persistent Dynamic Security configuration for first boot."
    mosquitto_ctrl dynsec init \
        "$temp_config" \
        "$admin_username" \
        "$DEVICEOPS_DYNSEC_ADMIN_PASSWORD" >/dev/null

    chown "$MOSQUITTO_UID:$MOSQUITTO_GID" "$temp_config"
    chmod 0600 "$temp_config"
    mv "$temp_config" "$DYNSEC_CONFIG"
    trap - EXIT HUP INT TERM
else
    echo "Reusing the persistent Dynamic Security configuration."
fi

chown -R "$MOSQUITTO_UID:$MOSQUITTO_GID" /mosquitto/data
chmod 0600 "$DYNSEC_CONFIG"

# Bootstrap credentials are not needed by the broker after initialization.
unset DEVICEOPS_DYNSEC_ADMIN_USERNAME
unset DEVICEOPS_DYNSEC_ADMIN_PASSWORD

exec "$@"
