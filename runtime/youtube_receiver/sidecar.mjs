#!/usr/bin/env node
import fs from "node:fs";
import process from "node:process";
import readline from "node:readline";
import YouTubeCastReceiver, { DefaultDataStore, Player } from "yt-cast-receiver";

function get(obj, key, fallback = null) {
  if (obj && Object.prototype.hasOwnProperty.call(obj, key)) {
    return obj[key];
  }
  return fallback;
}

function nested(obj, path, fallback = null) {
  let cur = obj;
  for (const segment of path) {
    if (cur && Object.prototype.hasOwnProperty.call(cur, segment)) {
      cur = cur[segment];
    } else {
      return fallback;
    }
  }
  return cur == null ? fallback : cur;
}

function errorText(error, fallback) {
  if (error && typeof error === "object" && "message" in error && error.message) {
    return String(error.message);
  }
  if (error) {
    return String(error);
  }
  return fallback;
}

function parseArgs(argv) {
  const out = {
    stateDir: "",
    deviceName: "RGBPI Mediaplayer",
    screenName: "YouTube on RGBPI",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--state-dir" && value) {
      out.stateDir = value;
      i += 1;
      continue;
    }
    if (key === "--device-name" && value) {
      out.deviceName = value;
      i += 1;
      continue;
    }
    if (key === "--screen-name" && value) {
      out.screenName = value;
      i += 1;
    }
  }
  return out;
}

function emit(event, payload = {}) {
  const msg = { event, ...payload };
  try {
    process.stdout.write(`${JSON.stringify(msg)}\n`);
  } catch (_err) {
    // Ignore JSON serialization/stream errors.
  }
}

class BridgePlayer extends Player {
  constructor() {
    super();
    this.position = 0;
    this.duration = 0;
    this.volume = { level: 72, muted: false };
    this.currentVideoId = null;
  }

  async doPlay(video, position) {
    this.position = Number.isFinite(position) ? Number(position) : 0;
    this.currentVideoId = get(video, "id", null);
    emit("play", {
      video_id: this.currentVideoId || "",
      position_seconds: this.position,
      queue_size: this.queue.length,
    });
    return true;
  }

  async doPause() {
    emit("pause");
    return true;
  }

  async doResume() {
    emit("resume");
    return true;
  }

  async doStop() {
    emit("stop");
    this.currentVideoId = null;
    this.position = 0;
    return true;
  }

  async doSeek(position) {
    this.position = Number.isFinite(position) ? Number(position) : this.position;
    emit("seek", { position_seconds: this.position });
    return true;
  }

  async doSetVolume(volume) {
    const level = Number(get(volume, "level", NaN));
    this.volume = {
      level: Number.isFinite(level) ? Math.max(0, Math.min(100, level)) : this.volume.level,
      muted: Boolean(get(volume, "muted", false)),
    };
    emit("volume", {
      level: this.volume.level,
      muted: this.volume.muted,
    });
    return true;
  }

  async doGetVolume() {
    return this.volume;
  }

  async doGetPosition() {
    return this.position;
  }

  async doGetDuration() {
    return this.duration;
  }
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.stateDir) {
    fs.mkdirSync(args.stateDir, { recursive: true });
    process.chdir(args.stateDir);
  }
  const dataStore = new DefaultDataStore();
  const player = new BridgePlayer();
  const receiver = new YouTubeCastReceiver(player, {
    dataStore,
    device: {
      name: args.deviceName,
      screenName: args.screenName,
      brand: "RGBPI",
      model: "CRT-Mediaplayer",
    },
    logLevel: "WARN",
  });
  const pairing = receiver.getPairingCodeRequestService();
  let pairingCode = "";
  let linkedState = "unlinked";

  function emitStatus() {
    emit("status", {
      state: linkedState,
      code: pairingCode,
      screen_name: args.screenName,
      queue_size: player.queue.length,
      receiver_version: "yt-cast-receiver@2.1.0",
    });
  }

  pairing.on("request", () => {
    linkedState = "code_pending";
    emit("link_state", {
      state: linkedState,
      code: pairingCode,
      screen_name: args.screenName,
      queue_size: player.queue.length,
    });
  });
  pairing.on("response", (code) => {
    pairingCode = String(code || "").trim();
    linkedState = "code_pending";
    emit("link_state", {
      state: linkedState,
      code: pairingCode,
      screen_name: args.screenName,
      queue_size: player.queue.length,
    });
  });
  pairing.on("error", (error) => {
    emit("receiver_error", { error: errorText(error, "pairing_error") });
  });
  receiver.on("senderConnect", () => {
    linkedState = "linked";
    emit("link_state", {
      state: linkedState,
      code: pairingCode,
      screen_name: args.screenName,
      queue_size: player.queue.length,
    });
  });
  receiver.on("senderDisconnect", () => {
    linkedState = receiver.getConnectedSenders().length > 0 ? "linked" : "code_pending";
    emit("link_state", {
      state: linkedState,
      code: pairingCode,
      screen_name: args.screenName,
      queue_size: player.queue.length,
    });
  });
  receiver.on("terminate", (error) => {
    emit("receiver_error", { error: errorText(error, "terminated") });
  });
  receiver.on("error", (error) => {
    emit("receiver_error", { error: errorText(error, "receiver_error") });
  });

  player.queue.on("videoAdded", (event) => {
    emit("queue_add", {
      video_id: String(get(event, "videoId", "") || ""),
      queue_size: player.queue.length,
    });
  });
  player.queue.on("videoSelected", (event) => {
    emit("queue_next", {
      video_id: String(get(event, "videoId", "") || ""),
      queue_size: player.queue.length,
    });
  });
  player.queue.on("playlistCleared", () => {
    emit("queue_clear", {
      queue_size: 0,
    });
  });
  player.on("state", (event) => {
    const queue = nested(event, ["current", "queue"], null);
    const queueIds = queue && Array.isArray(queue.videoIds) ? queue.videoIds : null;
    const current = nested(event, ["current"], null);
    const currentQueue = queue && queue.current ? queue.current : null;
    emit("player_state", {
      queue_size: queueIds ? queueIds.length : player.queue.length,
      player_status: String((current && current.status) || ""),
      video_id: String((currentQueue && currentQueue.id) || ""),
    });
  });

  await receiver.start();
  emit("receiver_ready", {
    screen_name: args.screenName,
    receiver_version: "yt-cast-receiver@2.1.0",
  });
  emitStatus();

  const rl = readline.createInterface({
    input: process.stdin,
    terminal: false,
  });

  rl.on("line", async (line) => {
    const raw = String(line || "").trim();
    if (!raw) {
      return;
    }
    let payload = {};
    try {
      payload = JSON.parse(raw);
    } catch (_err) {
      emit("receiver_error", { error: "invalid_command_json" });
      return;
    }
    const command = String(get(payload, "command", "") || "").trim().toLowerCase();
    try {
      if (command === "link_start") {
        linkedState = "code_pending";
        pairing.start();
        emitStatus();
        return;
      }
      if (command === "unlink") {
        pairing.stop();
        await receiver.stop();
        await dataStore.clear();
        pairingCode = "";
        linkedState = "unlinked";
        await receiver.start();
        emit("link_state", {
          state: linkedState,
          code: "",
          screen_name: args.screenName,
          queue_size: player.queue.length,
        });
        return;
      }
      if (command === "queue_next") {
        await player.next();
        emitStatus();
        return;
      }
      if (command === "queue_clear") {
        await player.reset();
        emit("queue_clear", { queue_size: 0 });
        emitStatus();
        return;
      }
      if (command === "shutdown") {
        rl.close();
        return;
      }
      if (command === "health") {
        emitStatus();
        return;
      }
    } catch (error) {
      emit("receiver_error", { error: errorText(error, "command_error") });
    }
  });

  rl.on("close", async () => {
    try {
      pairing.stop();
    } catch (_err) {
      // Ignore shutdown errors.
    }
    try {
      await receiver.stop();
    } catch (_err) {
      // Ignore shutdown errors.
    }
    process.exit(0);
  });
}

main().catch((error) => {
  emit("receiver_error", { error: errorText(error, "startup_error") });
  process.exit(1);
});
