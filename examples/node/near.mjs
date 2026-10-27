// Aircraft within a radius of a point, with Node.js 18+ (built-in fetch, no dependencies).
//
//   export FLYITALYADSB_API_KEY=...   # free: https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key
//   node near.mjs                     # 50 km around New York JFK
//   node near.mjs 48.35 11.79 25      # 25 km around Munich airport
//
// Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0

const [lat = 40.64, lon = -73.78, km = 50] = process.argv.slice(2).map(Number);
const key = process.env.FLYITALYADSB_API_KEY;
if (!key) {
  console.error("Set FLYITALYADSB_API_KEY first.");
  process.exit(1);
}

const res = await fetch(`https://api.flyitalyadsb.com/v2/lat/${lat}/lon/${lon}/dist/${km}`, {
  headers: { "X-Api-Key": key, "User-Agent": "my-app/1.0" },
});

if (!res.ok) {
  const body = await res.text();
  // 401 bad key, 403 radius above your plan (max_radius_km in the body),
  // 429 over the limit: wait Retry-After seconds. Refused requests are not counted.
  console.error(`HTTP ${res.status}`, res.headers.get("retry-after") ?? "", body.slice(0, 300));
  process.exit(1);
}

const { count, ac } = await res.json();
console.log(`${count} aircraft within ${km} km of ${lat}, ${lon}`);
console.log(`plan ${res.headers.get("x-fia-plan")}, ${res.headers.get("x-fia-used-month")} requests used this month`);

const isMilitary = (a) => ((a.dbFlags ?? 0) & 1) === 1;
for (const a of ac.filter((a) => a.lat !== undefined)) {
  const alt = a.alt_baro === "ground" ? "ground" : `${a.alt_baro ?? "?"} ft`;
  console.log(
    [
      ((a.flight ?? "").trim() || "-").padEnd(8),
      (a.r ?? "-").padEnd(8),
      (a.t ?? "-").padEnd(5),
      alt.padStart(9),
      `${Math.round(a.gs ?? 0)} kt`.padStart(7),
      a.squawk ?? "    ",
      a.type === "mlat" ? "MLAT" : "",
      isMilitary(a) ? "MIL" : "",
    ].join(" "),
  );
}
