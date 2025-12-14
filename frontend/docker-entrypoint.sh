#!/bin/sh
set -e

CONFIG_PATH="/usr/share/nginx/html/config.json"

if [ -n "${API_ORIGIN:-}" ]; then
	API_ORIGIN_JSON="\"${API_ORIGIN}\""
else
	API_ORIGIN_JSON="null"
fi

printf '{\n\t"api_origin": %s\n}\n' "$API_ORIGIN_JSON" > "$CONFIG_PATH"

exec nginx -g 'daemon off;'
