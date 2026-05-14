#!/bin/sh
set -eu

BUTTON_FILE="${1:-/tmp/weight_button}"
HOLD_SECONDS="${2:-2.2}"

printf 'press\n' > "$BUTTON_FILE"
sleep "$HOLD_SECONDS"
printf 'release\n' > "$BUTTON_FILE"
