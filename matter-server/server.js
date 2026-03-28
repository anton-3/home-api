#!/usr/bin/env node
/**
 * Matter bridge: bridged On/Off devices -> POST /garage on the local home-api FastAPI app.
 *
 * Env is loaded from the parent project `.env` via `load-parent-env.js` (see npm `start` script). Same keys as the
 * Python app: PORT (default 8000) builds `http://127.0.0.1:${PORT}`; AUTH_API_KEY is sent as X-API-Key when set.
 * Optional overrides: HOME_API_BASE_URL (full base URL), HOME_API_KEY (used before AUTH_API_KEY if both set).
 *
 * Also: GARAGE_MATTER_DEVICES (JSON array of { id, door, label, socket? | deviceType? }),
 * MATTER_PASSCODE, MATTER_DISCRIMINATOR, MATTER_PORT, MATTER_UNIQUE_ID, MATTER_VENDOR_ID, MATTER_PRODUCT_ID.
 * Matter persistence uses the default app storage dir (see startup log).
 */
import "@matter/main/platform";
import {
  Endpoint,
  Environment,
  ServerNode,
  StorageService,
  Time,
  VendorId,
} from "@matter/main";
import { BridgedDeviceBasicInformationServer } from "@matter/main/behaviors/bridged-device-basic-information";
import { OnOffLightDevice } from "@matter/main/devices/on-off-light";
import { OnOffPlugInUnitDevice } from "@matter/main/devices/on-off-plug-in-unit";
import { AggregatorEndpoint } from "@matter/main/endpoints/aggregator";

const DEFAULT_DEVICES = [
  { id: "north", door: "north", label: "North Garage", socket: false },
  { id: "south", door: "south", label: "South Garage", socket: true },
];

function parseEnvInt(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return fallback;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : fallback;
}

/** Loopback URL for the FastAPI app — same PORT as `app/__main__.py` / `.env`. */
function getHomeApiBaseUrl() {
  const override = process.env.HOME_API_BASE_URL?.trim();
  if (override) return override.replace(/\/$/, "");
  const port = parseEnvInt("PORT", 8000);
  return `http://127.0.0.1:${port}`;
}

/** Matches Python `AUTH_API_KEY`; HOME_API_KEY wins if set (matter-only override). */
function getGarageApiKey() {
  return (process.env.HOME_API_KEY ?? process.env.AUTH_API_KEY ?? "").trim();
}

function loadDevices() {
  const raw = process.env.GARAGE_MATTER_DEVICES?.trim();
  if (!raw) return DEFAULT_DEVICES;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) {
      throw new Error("GARAGE_MATTER_DEVICES must be a non-empty JSON array");
    }
    for (const d of parsed) {
      if (!d || typeof d.id !== "string" || !d.id.trim()) {
        throw new Error("Each device must have a non-empty string id");
      }
      if (typeof d.door !== "string" || !d.door.trim()) {
        throw new Error(`Device ${d.id}: door must be a non-empty string`);
      }
      if (typeof d.label !== "string" || !d.label.trim()) {
        throw new Error(`Device ${d.id}: label must be a non-empty string`);
      }
    }
    return parsed.map((d) => ({
      id: d.id.trim(),
      door: d.door.trim(),
      label: d.label.trim(),
      socket:
        d.socket === true ||
        (typeof d.deviceType === "string" && d.deviceType.toLowerCase() === "socket"),
    }));
  } catch (e) {
    console.error("Failed to parse GARAGE_MATTER_DEVICES:", e.message);
    throw e;
  }
}

async function postGarage(door) {
  const base = getHomeApiBaseUrl();
  const url = `${base}/garage`;
  const headers = { "Content-Type": "application/json" };
  const key = getGarageApiKey();
  if (key) headers["X-API-Key"] = key;

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ door }),
  });
  const text = await res.text();
  if (!res.ok) {
    console.error(`Garage API HTTP ${res.status}: ${text}`);
    throw new Error(`Garage API returned ${res.status}`);
  }
  console.log(`Garage API ok (door=${door}): ${text}`);
}

async function getMatterStartupConfig() {
  const environment = Environment.default;
  const storageService = environment.get(StorageService);
  console.log(`Matter storage directory: ${storageService.location}`);
  console.log(
    "Use matter.js --storage-path=... or env the CLI documents to relocate storage; avoid clashing with other Matter apps.",
  );

  const storageManager = await storageService.open("garage-bridge-device");
  const deviceStorage = storageManager.createContext("data");

  const passcode = parseEnvInt("MATTER_PASSCODE", await deviceStorage.get("passcode", 20202021));
  const discriminator = parseEnvInt("MATTER_DISCRIMINATOR", await deviceStorage.get("discriminator", 3840));
  const vendorId = parseEnvInt("MATTER_VENDOR_ID", await deviceStorage.get("vendorid", 0xfff1));
  const productId = parseEnvInt("MATTER_PRODUCT_ID", await deviceStorage.get("productid", 0x8000));
  const port = parseEnvInt("MATTER_PORT", await deviceStorage.get("port", 5540));
  const uniqueId =
    process.env.MATTER_UNIQUE_ID?.trim() ||
    (await deviceStorage.get("uniqueid", Time.nowMs.toString()));

  await deviceStorage.set({
    passcode,
    discriminator,
    vendorid: vendorId,
    productid: productId,
    port,
    uniqueid: uniqueId,
  });
  await storageManager.close();

  return {
    passcode,
    discriminator,
    vendorId,
    productId,
    port,
    uniqueId,
  };
}

function buildBridgedEndpoint(device) {
  const { id, label, socket } = device;
  const serialNumber = `garage-matter-${id}`;

  const type = socket
    ? OnOffPlugInUnitDevice.with(BridgedDeviceBasicInformationServer)
    : OnOffLightDevice.with(BridgedDeviceBasicInformationServer);

  return new Endpoint(type, {
    id,
    bridgedDeviceBasicInformation: {
      nodeLabel: label,
      productName: label,
      productLabel: label,
      serialNumber,
      reachable: true,
    },
  });
}

const devices = loadDevices();

console.log("home-api Matter bridge configuration:");
console.log(
  `  Garage API base: ${getHomeApiBaseUrl()} (${process.env.HOME_API_BASE_URL?.trim() ? "HOME_API_BASE_URL" : `PORT=${parseEnvInt("PORT", 8000)}`})`,
);
console.log(
  `  X-API-Key: ${getGarageApiKey() ? "(set)" : "(unset)"} (HOME_API_KEY or AUTH_API_KEY)`,
);
console.log(`  GARAGE_MATTER_DEVICES: ${process.env.GARAGE_MATTER_DEVICES ? "(custom JSON)" : "(defaults: north + south)"}`);
console.log(`  Devices (${devices.length}):`, devices.map((d) => `${d.label} -> door=${d.door}`).join("; "));

const matterConfig = await getMatterStartupConfig();

const deviceName = "Garage bridge";
const vendorName = "home-api";
const productName = "Garage Matter Bridge";

const server = await ServerNode.create({
  id: matterConfig.uniqueId,

  network: {
    port: matterConfig.port,
  },

  commissioning: {
    passcode: matterConfig.passcode,
    discriminator: matterConfig.discriminator,
  },

  productDescription: {
    name: deviceName,
    deviceType: AggregatorEndpoint.deviceType,
  },

  basicInformation: {
    vendorName,
    vendorId: VendorId(matterConfig.vendorId),
    nodeLabel: productName,
    productName,
    productLabel: productName,
    productId: matterConfig.productId,
    serialNumber: `matterjs-${matterConfig.uniqueId}`,
    uniqueId: matterConfig.uniqueId,
  },
});

const aggregator = new Endpoint(AggregatorEndpoint, { id: "aggregator" });
await server.add(aggregator);

for (const dev of devices) {
  const endpoint = buildBridgedEndpoint(dev);
  await aggregator.add(endpoint);

  endpoint.events.identify.startIdentifying.on(() => {
    console.log(`Identify started: ${dev.label}`);
  });
  endpoint.events.identify.stopIdentifying.on(() => {
    console.log(`Identify stopped: ${dev.label}`);
  });

  endpoint.events.onOff.onOff$Changed.on(async (value) => {
    if (!value) return;
    try {
      await postGarage(dev.door);
      await endpoint.set({ onOff: { onOff: false } });
    } catch (err) {
      console.error(`Failed to trigger ${dev.label}:`, err);
    }
  });
}

console.log(
  `Commissioning: passcode=${matterConfig.passcode} discriminator=${matterConfig.discriminator} matter UDP port=${matterConfig.port}`,
);
console.log("Pair from Google Home on the same LAN; QR/manual code is printed by matter.js when the server starts.");

await server.start();
