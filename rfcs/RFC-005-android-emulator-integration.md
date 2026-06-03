# RFC-005: Android Emulator Integration

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Run Android Emulator on the workstation for React Native and Flutter development, accessible via remote desktop.

## Motivation

Mobile development requires testing on actual device form factors. An emulator on the workstation enables:
- Full React Native development cycle
- Flutter app testing
- Android-specific debugging
- Screenshot-based UI testing

## Requirements

- Android SDK / Command-line tools
- KVM acceleration (nested virtualization)
- Sufficient RAM (4GB for emulator + 28GB for system)
- Remote desktop with smooth rendering

## Hetzner Cloud KVM Support

**Critical prerequisite:** Hetzner Cloud servers support nested virtualization (KVM) on dedicated CPU instances (CCX series). This must be verified:

```bash
egrep -c '(vmx|svm)' /proc/cpuinfo  # Should return > 0
```

CCX33 with AMD EPYC should support AMD-V/SVM.

## Installation Plan

```bash
# Android SDK command-line tools
mkdir -p /opt/android-sdk
wget https://dl.google.com/android/repository/commandlinetools-linux-latest.zip
unzip -d /opt/android-sdk/cmdline-tools ...

# Install platform tools and emulator
sdkmanager "platform-tools" "emulator" "platforms;android-34" "system-images;android-34;google_apis;x86_64"

# Create AVD
avdmanager create avd -n agent-phone -k "system-images;android-34;google_apis;x86_64" -d pixel_6

# Run (headless or with display)
emulator -avd agent-phone -no-window -gpu swiftshader_indirect
# Or with display for remote desktop:
emulator -avd agent-phone -gpu swiftshader_indirect
```

## Resource Allocation

| Resource | Emulator | Remaining |
|----------|----------|-----------|
| RAM | 4 GB | 28 GB |
| CPU | 2 cores | 6 cores |
| Disk | ~10 GB | 230 GB |

## Remote Desktop Considerations

- Emulator renders via software GPU (swiftshader) — no hardware GPU available
- Expect 15-30 FPS in remote desktop
- Sunshine/Moonlight would give better performance than xRDP for this use case
- Consider headless mode + ADB screenshots for automated testing

## Integration with UI Bridge

- ADB provides `uiautomator dump` for view hierarchy
- Layout Inspector data can be exported
- React Native inspector accessible via ADB port forward
- Flutter VM service accessible via ADB port forward

## Open Questions

1. Performance acceptable without hardware GPU?
2. Should we allocate a dedicated GPU via RunPod for emulator rendering?
3. Emulator farms (multiple devices) — resource limits?
4. iOS testing requires macOS — cloud Mac instances?
