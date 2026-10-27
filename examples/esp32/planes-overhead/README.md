# Planes overhead: ESP32 flight display

An ESP32 that shows the aircraft nearest to you (callsign, type, altitude, distance and direction) every 30 seconds, from the FlyItalyADSB API. It prints to the serial monitor, or to a 128×64 SSD1306 OLED.

```
7 aircraft within 15 km
SHT3A    A320   200 ft   2.1 km NE
LHX7H    A20N  1350 ft   2.5 km W
EIN168   A20N   850 ft   5.9 km E
SHT2N    A320  3275 ft   8.9 km W
```

That is real output around London Heathrow on 27 October 2026, produced by the sketch's own parsing code from a live API response. Aircraft on the ground are left out unless you set `SHOW_GROUND` to `true`.

## You need

- Any ESP32 board, with the [Arduino-ESP32 core](https://github.com/espressif/arduino-esp32) 3.x (Arduino IDE: Boards Manager → "esp32" by Espressif).
- The **ArduinoJson** library, version 7 (Library Manager).
- Optional: an SSD1306 128×64 I2C OLED and the **Adafruit SSD1306** + **Adafruit GFX** libraries. Wire VCC to 3V3, GND to GND, SDA and SCL to your board's default I2C pins (GPIO 21 and 22 on most ESP32 DevKit boards).
- A free API key: [get one here](https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key).

## Set up

1. Copy `secrets.example.h` to `secrets.h` (git-ignored) and fill in your Wi-Fi, your key and where the display sits (decimal degrees).
2. For the OLED, set `#define USE_OLED 1` at the top of `planes-overhead.ino`.
3. Upload and open the serial monitor at 115200 baud.

With [arduino-cli](https://arduino.github.io/arduino-cli/):

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 examples/esp32/planes-overhead
arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 examples/esp32/planes-overhead
```

## How many requests

One request every 30 seconds is 86,400 requests a month: compare it with your plan's monthly quota in the [plans table](../../../README.md#plans-and-limits). A 15 km radius answers in about 11 KB around Heathrow; the sketch reads the answer as a stream and keeps only the five fields it shows, so RAM use stays small. Change `RADIUS_KM`, `EVERY_MS` and `SHOW_GROUND` at the top of the sketch; the data itself refreshes every 2 seconds.

On a `429` the sketch waits the `Retry-After` seconds. Refused requests are not counted.

## Selling it?

You can, on every plan, Free included, within its limits.

- **One key for the whole product.** Every unit's requests count on that key. Size it as requests per minute per unit × units: the [plans](https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#piani).
- **From a few dozen units, use your own server.** A key in firmware can be extracted, and usage grows with every unit sold. Let your server fetch once (your customers' area, or the whole world on Pro) and have the units ask it: [`cache_server.py`](../../python/cache_server.py). That stays at 86,400 requests a month however many units you sell.
- **Credit the data** on the device, in its manual or on the product page: `Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0`. The OLED version shows the short form at the bottom of the screen.
- The feeder perk (Pro limits for people who run a receiver) is for non-commercial use: it doesn't cover units you sell.

More in the [displays and devices guide](https://flyitalyadsb.com/en/data/products/displays-and-devices/?utm_source=github&utm_campaign=adsb-api).

## TLS

The sketch checks the server's certificate against the root certificates in `root_ca.h`: the certificate authorities the API's TLS certificate can come from. If the display ever stops connecting with a TLS error after working before, update `root_ca.h` from this repository.
