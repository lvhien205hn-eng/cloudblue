# BlueRoblox Stream v2 (BRS2) — giao thức phát hình cho app PC + app Android

The web no longer streams. Customers control their phone only from the native apps (Windows PC app and Android app).
Every Windows server ("node") runs `bluestream.py`. The streamer captures the emulator window on the host with
Windows Graphics Capture, encodes it with NVENC (or x264 as a fallback), and sends one H.264 frame per message.
Input goes back to Android through scrcpy-server 2.4 running in control-only mode.

All integers are **big-endian**. Text is **UTF-8**. JSON is UTF-8 JSON without BOM.

---------------------------------------------------------------------------------------------------

## 1. Discovery (which server, how to connect)

The app logs in with Supabase (unchanged: `POST {SB}/auth/v1/token?grant_type=password`, publishable key).

Then it calls the RPC (user token):

```
POST {SB}/rest/v1/rpc/cloudphone_endpoint      body: {"p_id": "<phone uuid>"}
```

Response:

```json
{
  "node": "win1",
  "online": true,
  "status": "active",
  "name": "Máy 8GB",
  "android": "9",
  "engine": "ld",
  "stream": {
    "direct": [ {"host": "192.168.1.6", "port": 8189, "lan": true},
                {"host": "1.54.69.205", "port": 8189} ],
    "cert":   "5f1c…e2",                                  // sha256 of the server TLS cert (DER), hex lowercase
    "ws":     "wss://stream.cloudblue.vn/v2/stream",      // may be null/missing
    "api":    "https://phone.cloudblue.vn"                // cpapi base for actions (reboot, upload…)
  }
}
```

Errors (PostgREST error message): `NOT_LOGGED_IN`, `NOT_FOUND`, `NOT_ALLOWED`.
If `online` is false or `stream.direct` is empty and `stream.ws` is empty, show "Máy chủ đang bảo trì / offline".

## 2. Transports (try in this order)

1. Every `direct` entry with `"lan": true`. TCP connect timeout **400 ms**.
2. Every other `direct` entry. TCP connect timeout **2000 ms**.
3. `ws` (WebSocket over Cloudflare). Connect timeout 8 s.

Remember which path worked last time per node and try it first next time (but keep the list order otherwise).

### 2a. Direct = TLS over TCP

* Plain TCP to `host:port`, then a TLS client handshake. Do **not** verify the CA chain or hostname.
  Instead compute SHA-256 over the **leaf certificate DER bytes** and compare it (case-insensitive hex)
  with `stream.cert`. If it differs, close and try the next path. If `cert` is empty, skip direct paths.
* After the handshake every message is framed as:

```
[length u32][type u8][payload …]      length = 1 + payload length   (max 8 MiB)
```

* Set TCP_NODELAY on the socket.

### 2b. WebSocket

* Standard RFC 6455 client to the `ws` URL (wss). Each **binary** message is `[type u8][payload …]`.
  Ignore text messages. No extra length prefix (the WebSocket frame gives the length).

## 3. Messages

### Client → server

| type | name | payload |
|---|---|---|
| `0x01` | HELLO | JSON, must be the **first** message (within 10 s): `{"v":2,"token":"<supabase access token>","phone":"<uuid>","client":"pc"\|"android","ver":"1.0.0","q":"auto"\|"eco"\|"bal"\|"hd","fps":60,"maxh":1280}` — `fps`, `maxh` optional |
| `0x10` | TOUCH | `action u8` (0 down · 1 up · 2 move · 3 cancel) · `pointer u8` (0–9) · `x u16` · `y u16` |
| `0x11` | KEY | `action u8` (0 down · 1 up) · `keycode u32` (Android KeyEvent code) · `meta u32` (Android meta state) |
| `0x12` | TEXT | UTF-8 text to type (server splits long text) |
| `0x13` | SCROLL | `x u16` · `y u16` · `h i16` · `v i16` — 120 = one wheel notch; v > 0 = wheel away from user (scroll up) |
| `0x14` | CMD | JSON `{"cmd": "back"\|"home"\|"recents"\|"power"\|"volup"\|"voldown"\|"rotate"\|"notif"\|"menu"}` |
| `0x15` | PING | `client_ms u64` |
| `0x16` | QUALITY | JSON `{"q":"eco"\|"bal"\|"hd"\|"auto", "fps": 60, "kbps": 4000}` — fps/kbps optional |
| `0x17` | KEYFRAME | empty — ask for a new keyframe (decoder error) |
| `0x18` | CLIP_SET | `paste u8` (1 = paste right away) · UTF-8 text → sets the phone clipboard |
| `0x19` | BYE | empty — client is closing on purpose |
| `0x1A` | ACK | `pts_us u64` = the `pts_us` of the newest VIDEO message received so far. Send it every ~100 ms while video flows (and right after each keyframe). The server uses it to measure how far behind the client is and drops frames instead of building up delay. |

* `x`,`y` are normalized over the **decoded video frame**: 0 = left/top, 65535 = right/bottom.
  The client letterboxes the video and must drop touches outside the picture.
* Multi-touch: send each pointer separately (down → moves → up) with its own `pointer` id.
  On ACTION_CANCEL send `3` for every pointer that is down.
* Moves: send at most one MOVE per pointer per ~8 ms (coalesce).

### Server → client

| type | name | payload |
|---|---|---|
| `0x81` | WELCOME | JSON `{"ok":true,"w":540,"h":960,"fps":60,"kbps":4000,"codec":"h264","enc":"nvenc"\|"x264","name":"…","android":"9","q":"bal"}` |
| `0x82` | VIDEO | `flags u8` (bit0 = keyframe, bit1 = contains SPS/PPS) · `pts_us u64` (server monotonic clock when the frame was encoded — opaque for the client, just echo it in ACK) · H.264 **Annex-B access unit** (start codes `00 00 00 01`) |
| `0x83` | SIZE | JSON `{"w":960,"h":540}` — the video size changed (rotation). A keyframe with SPS/PPS follows. Reconfigure the decoder. |
| `0x84` | CLIPBOARD | UTF-8 text the phone copied → put it on the PC/phone clipboard |
| `0x85` | PONG | `client_ms u64` (echo of PING) |
| `0x86` | ERROR | JSON `{"code":"AUTH"\|"NOT_YOURS"\|"OFFLINE"\|"LOCKED"\|"MAINT"\|"KICKED"\|"BUSY"\|"BAD"\|"INTERNAL","msg":"Vietnamese text for the user"}` — then the server closes |
| `0x87` | STATS | JSON `{"fps":59.8,"kbps":2100,"drop":0,"enc":"nvenc","q":"bal"}` every 2 s |

### Rules

* The first VIDEO after WELCOME and after every SIZE is a keyframe that starts with SPS + PPS.
* Each VIDEO message is **exactly one frame**. Decode it immediately and present it immediately
  (no jitter buffer, no timestamp pacing). H.264 profile: constrained baseline or main, **no B-frames**.
* One viewer per phone: a new HELLO for the same phone kicks the old session (`ERROR KICKED`).
  A client that receives `KICKED` must **not** auto-reconnect; show "Máy đang được mở ở nơi khác".
* Keepalive: client sends PING every 2 s. The server closes a session after 15 s without any client message.
  The client treats 6 s without any server message as a dead link and reconnects (backoff 0.5 s, 1 s, 2 s, 4 s, max 5 s).
  On `AUTH`, refresh the Supabase token once and reconnect; if it fails again, go back to login.
* After a reconnect the client must clear its decoder state and wait for the next keyframe.

### Android key codes used

BACK 4 · HOME 3 · APP_SWITCH 187 · MENU 82 · POWER 26 · VOLUME_UP 24 · VOLUME_DOWN 25 · DEL 67 · FORWARD_DEL 112 ·
ENTER 66 · TAB 61 · ESCAPE 111 · SPACE 62 · DPAD_UP 19 · DPAD_DOWN 20 · DPAD_LEFT 21 · DPAD_RIGHT 22 ·
MOVE_HOME 122 · MOVE_END 123 · PAGE_UP 92 · PAGE_DOWN 93 · A–Z 29–54 · 0–9 7–16.
Meta: SHIFT_ON 0x1 · ALT_ON 0x2 · CTRL_ON 0x1000 · META_ON 0x10000.

## 4. Actions that do not need the video link

Unchanged cpapi endpoints, called with `Authorization: Bearer <access token>` on `stream.api` (fallback `https://phone.cloudblue.vn`):

* `GET  {api}/cpapi/<phone id>/info` → status / online / booting
* `POST {api}/cpapi/<phone id>/reboot`
* `POST {api}/cpapi/<phone id>/upload?name=<file>` (APK/file, raw body, 8 MiB chunks with `&off=` like before)

## 5. Quality presets (server side)

| q | long side | fps | bitrate |
|---|---|---|---|
| eco | 960 | 30 | 1.5 Mbps |
| bal | 1280 | 60 | 3 Mbps |
| hd | 1600 | 60 | 6 Mbps |
| auto | same as bal (default) | | |

The server never upscales: the long side is min(window size, preset). `fps` is also capped by the FPS the customer bought.

**Bitrate adapts automatically in every mode** (the preset/requested value is only the ceiling):
the server measures what the client really received from the ACKs. On congestion it drops to
goodput × 0.8 (at least 250 kbps, at most 0.7 × current); after 10 s without congestion it steps back up × 1.3
until the ceiling. Below 1.4 Mbps the frame rate is capped at 30 fps, below 0.7 Mbps at 20 fps.
Every change restarts the encoder, so the client gets a fresh keyframe with SPS/PPS (same size → no SIZE message).

---------------------------------------------------------------------------------------------------

## 6. Real PC machines (VPS GPU) — relay mode (pcrelay 21/11a · SQL v43 · agent 21.11d+)

A rented Windows PC sits behind the shop's router, so nobody can connect to it. The helper `pcremote.py` on the PC
connects **out** to the stream port of one cloud-phone server and waits there. The viewer (web `play.html?pc=…`,
Android app, PC app) connects to the same server exactly like for a phone; the server (`pcrelay.py` inside
`bluestream.py`) pairs both links and only forwards packets (it never decodes video or reads keys).

### 6a. Discovery

```
POST {SB}/rest/v1/rpc/pc_endpoint      body: {"p_id": "<pc uuid>"}          (user token)
```

Same shape as `cloudphone_endpoint` plus `"kind": "pc"`, `"engine": "pc"`, `"android": "pc"`, `"os": "22h2"|"1511"`,
`"code"` (machine number) and `"until"` (rental end, unix seconds or null). `online` = the PC is connected to a live relay;
`stream` describes that relay node. Errors: `NOT_LOGGED_IN`, `NOT_FOUND`, `NOT_ALLOWED` (only the assigned customer
— `pc_machines.user_id` — or an admin). Function missing (`PGRST202`) = the shop has not run SQL v43 yet.
Offline: show "Máy PC đang tắt / chưa nối máy chủ" and retry every 10 s.

### 6b. Session

* HELLO is the same as section 3 but with `"pc": "<pc uuid>"` **instead of** `"phone"`.
* WELCOME adds `"kind": "pc"`; `w`/`h` = the PC screen scaled (long side ≤ 1920, `eco` 1280, or `maxh`). Errors: `AUTH` · `NOT_YOURS` ·
  `LOCKED` (rental expired, or remote control turned off for this PC / for all PCs) · `OFFLINE` (PC not connected,
  or nobody logged in / screen locked) · `MAINT` (site maintenance) · `KICKED` (opened somewhere else — one viewer
  per PC, like phones) · `BUSY` / `BAD`. Admins are never blocked by `LOCKED`.
* Video, PING/PONG, ACK, QUALITY, KEYFRAME, CLIP_SET, CLIPBOARD, STATS: unchanged.
* When an admin who is **not** the machine's customer opens it, the PC shows a message box so the customer knows.
* The PC only captures the screen while a viewer is connected (the relay sends start / stop to the PC).

### 6c. Input (client → server)

| type | name | payload |
|---|---|---|
| `0x1B` | MOUSE | `action u8` (0 move · 1 down · 2 up) · `button u8` (0 left · 1 right · 2 middle · 3 back/X1 · 4 forward/X2) · `x u16` · `y u16` |
| `0x10` | TOUCH | still accepted (touch screens / phone app): tap = left click · hold still 0.55 s = right click · tap and drag = drag · double tap = double click · two-finger swipe = wheel |
| `0x13` | SCROLL | real mouse wheel at `x`,`y` (120 = one notch; `h` = horizontal wheel) |
| `0x11` | KEY | Android key code as in section 3 → Windows virtual key on the PC (table below). Send down **and** up; the PC releases every key still held when the session closes |
| `0x12` | TEXT | Unicode text typed on the PC |
| `0x14` | CMD | `back` Esc · `home` / `desktop` Win+D · `recents` Win+Tab · `win` Win · `alttab` Alt+Tab · `altf4` Alt+F4 · `taskmgr` Ctrl+Shift+Esc · `explorer` Win+E · `notif` Win+A · `menu` context menu · `enter` · `mute` · `volup` · `voldown` (`power`, `rotate` ignored) |

`x`,`y` are normalized over the decoded video like TOUCH (0…65535). Send MOVE at most every ~8 ms while the pointer
moves (with or without a button held). Release all keys and buttons when the window loses focus.

Extra key codes for a real PC (besides section 3): F1–F12 131–142 · SHIFT_LEFT 59 · SHIFT_RIGHT 60 · CTRL_LEFT 113 ·
CTRL_RIGHT 114 · ALT_LEFT 57 · ALT_RIGHT 58 · META_LEFT (Win) 117 · META_RIGHT 118 · INSERT 124 · CAPS_LOCK 115 ·
NUM_LOCK 143 · SCROLL_LOCK 116 · SYSRQ (Print Screen) 120 · BREAK 121 · NUMPAD_0–9 144–153 · NUMPAD ÷ × − + . 154–158 ·
NUMPAD_ENTER 160 · GRAVE 68 · MINUS 69 · EQUALS 70 · [ 71 · ] 72 · \ 73 · ; 74 · ' 75 · , 55 · . 56 · / 76 · MUTE 164 ·
MEDIA play/pause 85 · next 87 · previous 88.

### 6d. PC ⇄ relay (internal, `windows/pcrelay.py` + `winpc/agent/pcremote.py`)

The PC asks Supabase where to connect (`pc_relay_where`, machine id + machine token), connects to that node with the
same framing as section 2, then sends `P_HELLO 0x02` `{"pc", "token", …}`. The relay checks it with `pc_relay_auth`
(service key, never on the PC) and answers `R_OK 0x90`. When a viewer arrives: `R_START 0x91` → the PC starts capture
and sends `P_INFO 0x03` `{sid, w, h, …}` → the relay sends WELCOME. `R_STOP 0x92` = no viewer left (capture stops),
`R_SLOW 0x93` = the viewer is behind (lower the bitrate). Relays report live PCs with `pc_relay_seen` every 40 s;
a PC not reported for 100 s counts as offline. Disable the relay on a server: `PC_RELAY=0` in `cloudphone.conf`.
