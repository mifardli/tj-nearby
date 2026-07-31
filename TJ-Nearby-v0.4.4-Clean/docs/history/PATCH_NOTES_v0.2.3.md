# TJ Nearby v0.2.3

- Fixed PyObjC `Delegate is overriding existing Objective-C class`.
- Core Location and authorization delegate classes now have stable, unique Objective-C names.
- Registered Objective-C delegate classes are looked up and reused across repeated checks.
- The menu-bar app retains a single authorization manager while macOS permission is pending.
- Location manager delegates are detached after a completed location request.
