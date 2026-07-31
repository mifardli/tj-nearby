# Patch Notes v0.2.6

## Strict direction validation

Notifications no longer trust the first GTFS route variant that geometrically matches a bus. Direction is resolved using independent evidence, in descending strength:

- exact live `trip_id` mapped to the GTFS trip variant;
- live `direction_id` when it is explicitly `0` or `1`;
- live destination/headsign text;
- ordered live `next_stops` and `previous_stops` matched against GTFS stop order;
- forward progress on the GTFS shape and stop sequence.

A destination is marked **confirmed** only when a live direction signal agrees with forward GTFS geometry/order. Shape proximity alone is not sufficient.

When two different headsigns remain similarly plausible, the app reports `Arah belum pasti`, marks the arrival ambiguous, and does not send a notification. This prevents a shared corridor or branching route such as 4D from being labelled with the wrong terminal.

## Notification presentation

Confirmed notifications use this compact structure:

- title: `4D → Pulo Gadung · 7 menit`;
- subtitle: `Bus DM-xxxx · 2 halte lagi`;
- body: `Menuju Halte Kuningan Madya · 135 m dari lokasi lo (jalan ±2 menit).`

The notification cooldown key now includes direction and headsign. A bus that later begins a genuine reverse-direction trip can notify again, while a single polling cycle still produces only one alert for the same physical bus.

## Diagnostics

App diagnostics now include:

- direction status (`confirmed`, `estimated`, or `ambiguous`);
- direction confidence and score;
- evidence used for the decision;
- reason an arrival was or was not eligible for notification.
