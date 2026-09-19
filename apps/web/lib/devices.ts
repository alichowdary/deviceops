import type { Device } from "./types";

export function formatDeviceLabel(device: Device): string {
  return device.display_name
    ? `${device.display_name} · ${device.device_id}`
    : device.device_id;
}

export function deviceLabelForId(
  devices: Device[],
  deviceId: string,
): string {
  const device = devices.find((candidate) => candidate.device_id === deviceId);
  return device ? formatDeviceLabel(device) : deviceId;
}
