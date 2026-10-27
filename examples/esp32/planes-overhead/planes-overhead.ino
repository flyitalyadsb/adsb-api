// Planes overhead: an ESP32 desk display of the aircraft nearest to you,
// from the FlyItalyADSB API (https://api.flyitalyadsb.com/v2).
//
// Board: any ESP32, Arduino-ESP32 core 3.x. Library: ArduinoJson 7.
// Prints to the serial monitor; set USE_OLED to 1 for a 128x64 SSD1306 I2C OLED
// (libraries Adafruit SSD1306 + Adafruit GFX; SDA/SCL on the board's default pins).
//
// 1. Copy secrets.example.h to secrets.h and fill it in (free key, Wi-Fi, your position).
// 2. Upload, open the serial monitor at 115200 baud.
//
// Requests: one every 30 s = 86,400 a month, within the Free plan (300,000/month).
// Selling these? Use one key for the whole product: every unit counts on it. From a few
// dozen units, let your own server fetch once and the units ask it
// (see examples/python/cache_server.py). The feeder perk does not cover units you sell.
//
// Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
// Put that line on the device, in its manual or on its product page.

#ifndef USE_OLED
#define USE_OLED 0
#endif

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <limits.h>
#include <math.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "secrets.h not found: copy secrets.example.h to secrets.h and fill it in"
#include "secrets.example.h"
#endif

#include "root_ca.h"

#if USE_OLED
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
#endif

const float RADIUS_KM = 15;        // 15 km: about 11 KB around Heathrow; 50 km over New York is ~60 KB
const uint32_t EVERY_MS = 30000;   // the data refreshes every 2 s; 30 s is plenty for a display
const int MAX_PLANES = 8;
const bool SHOW_GROUND = false;   // aircraft on the ground (taxiing, parked) are left out

struct Plane {
  char callsign[9];
  char type[5];
  long altFt;      // feet; LONG_MIN when on the ground
  float km;
  const char* dir; // compass direction from you
};

Plane planes[MAX_PLANES];
int planeCount = 0;
int shownTotal = 0;  // aircraft that passed the filters, before keeping the nearest
uint32_t waitMs = EVERY_MS;

float distanceKm(float lat1, float lon1, float lat2, float lon2) {
  const float p = M_PI / 180;
  float h = sq(sinf((lat2 - lat1) * p / 2)) +
            cosf(lat1 * p) * cosf(lat2 * p) * sq(sinf((lon2 - lon1) * p / 2));
  return 12742 * asinf(sqrtf(h));
}

const char* compass(float lat1, float lon1, float lat2, float lon2) {
  static const char* names[] = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"};
  const float p = M_PI / 180;
  float y = sinf((lon2 - lon1) * p) * cosf(lat2 * p);
  float x = cosf(lat1 * p) * sinf(lat2 * p) - sinf(lat1 * p) * cosf(lat2 * p) * cosf((lon2 - lon1) * p);
  float deg = fmodf(atan2f(y, x) / p + 360, 360);
  return names[(int)roundf(deg / 45) % 8];
}

// Keeps the MAX_PLANES nearest, sorted by distance.
void addPlane(const Plane& p) {
  if (planeCount == MAX_PLANES && p.km >= planes[MAX_PLANES - 1].km) return;
  int i = planeCount < MAX_PLANES ? planeCount++ : MAX_PLANES - 1;
  while (i > 0 && planes[i - 1].km > p.km) {
    planes[i] = planes[i - 1];
    i--;
  }
  planes[i] = p;
}

bool fetchPlanes() {
  char url[100];
  snprintf(url, sizeof url, "https://api.flyitalyadsb.com/v2/lat/%.4f/lon/%.4f/dist/%.0f",
           (double)HOME_LAT, (double)HOME_LON, (double)RADIUS_KM);

  WiFiClientSecure tls;
  tls.setCACert(ROOT_CA);
  HTTPClient http;
  http.useHTTP10(true);  // no chunked encoding, so ArduinoJson can read the stream directly
  if (!http.begin(tls, url)) return false;
  http.addHeader("X-Api-Key", FLYITALYADSB_API_KEY);
  http.setUserAgent("planes-overhead-esp32/1.0");
  const char* wanted[] = {"Retry-After"};
  http.collectHeaders(wanted, 1);

  int status = http.GET();
  if (status != 200) {
    // 401: check the key. 403: radius above your plan. 429: over the limit, wait Retry-After.
    Serial.printf("HTTP %d %s\n", status, status < 0 ? http.errorToString(status).c_str() : "");
    if (status == 429 && http.hasHeader("Retry-After")) {
      waitMs = max<uint32_t>(EVERY_MS, http.header("Retry-After").toInt() * 1000UL);
    }
    http.end();
    return false;
  }

  JsonDocument filter;  // keep only what the display shows: a small answer stays small in RAM
  JsonObject f = filter["ac"].add<JsonObject>();
  f["flight"] = true;
  f["t"] = true;
  f["alt_baro"] = true;
  f["lat"] = true;
  f["lon"] = true;

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
  http.end();
  if (err) {
    Serial.printf("JSON error: %s\n", err.c_str());
    return false;
  }

  planeCount = 0;
  shownTotal = 0;
  for (JsonObject a : doc["ac"].as<JsonArray>()) {
    if (!a["lat"].is<float>()) continue;  // no position yet
    Plane p;
    strlcpy(p.callsign, a["flight"] | "-", sizeof p.callsign);
    for (int i = strlen(p.callsign) - 1; i >= 0 && p.callsign[i] == ' '; i--) p.callsign[i] = 0;
    strlcpy(p.type, a["t"] | "?", sizeof p.type);
    p.altFt = a["alt_baro"].is<const char*>() ? LONG_MIN : (long)(a["alt_baro"] | 0);  // "ground"
    if (p.altFt == LONG_MIN && !SHOW_GROUND) continue;
    shownTotal++;
    float lat = a["lat"], lon = a["lon"];
    p.km = distanceKm(HOME_LAT, HOME_LON, lat, lon);
    p.dir = compass(HOME_LAT, HOME_LON, lat, lon);
    addPlane(p);
  }
  return true;
}

void show() {
  char alt[12];
  Serial.printf("\n%d aircraft within %.0f km\n", shownTotal, RADIUS_KM);
  for (int i = 0; i < planeCount; i++) {
    if (planes[i].altFt == LONG_MIN) strlcpy(alt, "ground", sizeof alt);
    else snprintf(alt, sizeof alt, "%ld ft", planes[i].altFt);
    Serial.printf("%-8s %-4s %8s %5.1f km %s\n", planes[i].callsign, planes[i].type, alt,
                  planes[i].km, planes[i].dir);
  }
#if USE_OLED
  oled.clearDisplay();
  oled.setCursor(0, 0);
  oled.printf("%d aircraft in %.0f km\n", shownTotal, RADIUS_KM);
  for (int i = 0; i < planeCount && i < 6; i++) {  // 21 characters a line
    if (planes[i].altFt == LONG_MIN) strlcpy(alt, "gnd", sizeof alt);
    else snprintf(alt, sizeof alt, "%ld", planes[i].altFt);
    oled.printf("%-7.7s%-4s%6s%4.0f\n", planes[i].callsign, planes[i].type, alt, planes[i].km);
  }
  oled.setCursor(0, 56);
  oled.print("Data:flyitalyadsb.com");  // the short credit line
  oled.display();
#endif
}

void setup() {
  Serial.begin(115200);
#if USE_OLED
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextWrap(false);
  oled.clearDisplay();
  oled.print("Connecting...");
  oled.display();
#endif
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  configTime(0, 0, "pool.ntp.org");  // a correct clock for checking the server certificate
  Serial.println("Wi-Fi connected");
}

void loop() {
  waitMs = EVERY_MS;
  if (fetchPlanes()) show();
  delay(waitMs);
}
