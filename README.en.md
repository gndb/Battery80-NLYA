# Battery80 NLYA portable runtime

Windows x64 native 80% battery maintenance panel for **THUNDEROBOT NLYA / TP181 / IT5570 rev07 / C009A0** only.

Download the runtime ZIP from GitHub Releases, extract the entire folder, and double-click `BatteryPanel.exe`. No Python installation, PowerShell7, or ROM import is required. Keep `_internal` and `drivers` next to the exe.

Confirm the deployment folder and temporary signed driver use; choose Open Panel and accept UAC. Launch reads state only; enabling is a separate action. Simulation preview requires no driver. Above 80% the OEM policy may actively discharge. Successful close keeps the policy; reopen and cancel maintenance to restore default charging.

The embedded analysis record is provenance, not cryptographic attestation of the running EC image. Hardware identity, driver signature/hash, fixed commands, fault journals and recovery gates remain. No BIOS/EC firmware bytes are distributed.

The packaged release has offline/simulation validation only. Prior machine-specific observations do not certify a new deployment, full charging cycles, sleep or reboot persistence. See [validation](docs/VALIDATION.md), [usage](docs/USAGE.md), [building](docs/DEVELOPMENT.md), [license status](LICENSE_STATUS.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

Version 0.2.1 includes the current black-and-gold panel. Charging protocol, identity checks, fault locks and recovery behavior remain unchanged. The application was rebuilt and validated offline; no new live hardware acceptance is implied. See [release notes](RELEASE_NOTES.md).
