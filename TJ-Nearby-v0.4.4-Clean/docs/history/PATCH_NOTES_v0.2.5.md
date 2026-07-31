# Patch Notes v0.2.5

## Notification mode changed to every approaching bus

TJ Nearby now defaults to `notification.mode: all_arrivals`.

For every newly detected physical bus that is estimated to approach one of the nearby public-stop groups, the app sends one notification containing:

- route code;
- destination/headsign;
- estimated arrival time;
- target nearby stop;
- bus body/identifier;
- walking distance and estimated walking time.

A bus is notified only once per live trip/route occurrence. Multiple GTFS platforms or route variants do not create duplicate alerts for the same physical bus. The normal polling interval remains 30 seconds.

The previous behavior remains available as `notification.mode: leave_now`.
