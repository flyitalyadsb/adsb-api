#!/bin/sh
# The FlyItalyADSB API with curl (and jq to read the answers). Each block is one request.
#
#   export FLYITALYADSB_API_KEY=...   # free: https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key
#   sh curl.sh
#
# Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
set -eu
: "${FLYITALYADSB_API_KEY:?set FLYITALYADSB_API_KEY first}"
API=https://api.flyitalyadsb.com/v2
fia() { curl -sS --compressed -A "my-app/1.0" -H "X-Api-Key: $FLYITALYADSB_API_KEY" "$API$1"; }

echo "## Every aircraft within 25 km of London Heathrow (radius in km)"
NEAR=$(fia /lat/51.47/lon/-0.45/dist/25)
echo "$NEAR" | jq -r '"\(.count) aircraft",
  (.ac[] | [(.flight // "-" | sub(" +$"; "")), .r, .t, (.alt_baro | tostring)] | @tsv)'

echo "## One aircraft by callsign (also /reg/{reg} and /icao/{hex}; 404 when it isn't flying now)"
CALLSIGN=$(echo "$NEAR" | jq -r '[.ac[].flight // empty][0] // "BAW1" | sub(" +$"; "")')
fia "/callsign/$CALLSIGN" | jq '{hex, flight, r, t, lat, lon, alt_baro, gs, squawk}'

echo "## Emergencies right now, worldwide: squawk 7700 (also 7600, 7500)"
fia /sqk/7700 | jq -r '"\(.count) aircraft squawking 7700", (.ac[] | [.hex, .flight, .r, .t] | @tsv)'

echo "## Military aircraft the network sees now (dbFlags & 1)"
fia /mil | jq -r '"\(.count) military aircraft", (.ac[:10][] | [.hex, (.flight // "-"), .t] | @tsv)'

echo "## Your plan and usage are in the response headers"
curl -sS -o /dev/null -D - -A "my-app/1.0" -H "X-Api-Key: $FLYITALYADSB_API_KEY" "$API/sqk/7600" | grep -i '^x-fia-'

echo "## Coverage around Milan in the last 24 hours (no key needed, 30 requests/min per IP)"
curl -sS -A "my-app/1.0" "https://api.flyitalyadsb.com/api/coverage?lat=45.46&lon=9.19&radius=50" |
  jq '{aircraft_last_24h: .last_24h.aircraft, now: .now, receivers: .receivers}'
