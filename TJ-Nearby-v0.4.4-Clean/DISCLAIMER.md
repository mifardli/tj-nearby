# Data and API disclaimer

- GTFS static data is obtained from the official TransJakarta GTFS feed and remains subject to its publisher's terms and attribution requirements.
- The real-time API used by this experimental client is not documented here as an officially supported public API. Its endpoint, authentication flow, headers, response fields, and availability can change without notice.
- The application uses a small location-based polling radius and a configurable interval. Do not use it to bulk-archive the full fleet or overload TransJakarta infrastructure.
- Location is processed locally. This application does not intentionally store location history.
- Arrival times are estimates, not operational guarantees. Always account for traffic, walking conditions, stop access, and service changes.
- This project is not affiliated with or endorsed by PT Transportasi Jakarta.
