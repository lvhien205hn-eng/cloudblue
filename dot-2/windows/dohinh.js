// dohinh.js — ĐO luồng hình NGAY TRÊN MÁY CHỦ (không qua mạng, không qua trình duyệt)
//   node C:\blue\dohinh.js 127.0.0.1:5557 [giây=15] [fps=30] [bitrate=1800000] [cạnh dài=720]
// In: số khung/giây máy chủ thật sự gửi ra, khoảng cách giữa các khung (đều hay giật), dung lượng.
// → Máy chủ gửi đều ~30 khung/giây mà trên web vẫn lag = do ĐƯỜNG MẠNG / trình duyệt.
// → Máy chủ gửi ít khung / khoảng cách lớn = do BỘ NÉN trong máy ảo.
const path = require("path");
const WS = require(path.join("C:\\blue\\ws-scrcpy\\dist\\node_modules\\ws"));
const [udid = "127.0.0.1:5557", secS = "15", fpsS = "30", brS = "1800000", sizeS = "720"] = process.argv.slice(2);
const SEC = +secS, FPS = +fpsS, BR = +brS, SIZE = +sizeS;

function videoSettings() {           // giống VideoSettings.toBuffer() của ws-scrcpy (không codecOptions / encoderName)
  const b = Buffer.alloc(35); let o = 0;
  o = b.writeInt32BE(BR, o); o = b.writeInt32BE(FPS, o); o = b.writeInt8(2, o);          // bitrate, maxFps, iFrameInterval
  o = b.writeInt16BE(SIZE, o); o = b.writeInt16BE(SIZE, o);                              // bounds
  o = b.writeInt16BE(0, o); o = b.writeInt16BE(0, o); o = b.writeInt16BE(0, o); o = b.writeInt16BE(0, o);   // crop
  o = b.writeInt8(0, o); o = b.writeInt8(-1, o); o = b.writeInt32BE(0, o);              // sendFrameMeta, lockedOrientation, displayId
  o = b.writeInt32BE(0, o); b.writeInt32BE(0, o);                                        // codecOptions, encoderName
  return Buffer.concat([Buffer.from([101]), b]);                                         // TYPE_CHANGE_STREAM_PARAMETERS
}
const url = `ws://127.0.0.1:8000/?action=proxy-adb&remote=${encodeURIComponent("tcp:8886")}&udid=${encodeURIComponent(udid)}`;
const ws = new WS(url); ws.binaryType = "nodebuffer";
let t0 = 0, sent = false, frames = [], bytes = 0, first = 0;
const MAGIC = Buffer.from("scrcpy_initial");
ws.on("open", () => console.log("Đã nối trình phát hình của", udid));
ws.on("message", (d) => {
  if (!Buffer.isBuffer(d)) return;
  if (d.length > MAGIC.length && d.subarray(0, MAGIC.length).equals(MAGIC)) {
    if (!sent) { ws.send(videoSettings()); sent = true; t0 = Date.now(); console.log(`Gửi cài đặt: ${SIZE}px · ${(BR / 1e6).toFixed(1)} Mbps · ${FPS} FPS — đang đo ${SEC} giây…`); }
    return;
  }
  if (!t0) return;
  const now = Date.now(); bytes += d.length;
  for (let i = 0; i + 4 < d.length; i++) {                // đếm khung = đơn vị NAL loại 1 (thường) / 5 (khung khoá)
    if (d[i] === 0 && d[i + 1] === 0 && (d[i + 2] === 1 || (d[i + 2] === 0 && d[i + 3] === 1))) {
      const k = d[i + 2] === 1 ? i + 3 : i + 4, t = d[k] & 31;
      if (t === 1 || t === 5) { frames.push(now); if (!first) first = now - t0; break; }
    }
  }
});
ws.on("error", (e) => { console.log("LỖI:", e.message); process.exit(1); });
setTimeout(() => {
  ws.close();
  const f = frames.filter((t) => t - t0 > 2000);            // bỏ 2 giây đầu (khởi động bộ nén)
  const dur = (SEC * 1000 - 2000) / 1000;
  const gaps = f.slice(1).map((t, i) => t - f[i]).sort((a, b) => a - b);
  const q = (p) => gaps.length ? gaps[Math.min(gaps.length - 1, Math.floor(gaps.length * p))] : 0;
  console.log("================ KẾT QUẢ ================");
  console.log(`Khung đầu tiên sau: ${first} ms`);
  console.log(`Khung/giây máy chủ gửi ra: ${(f.length / dur).toFixed(1)}  (đặt ${FPS})`);
  console.log(`Khoảng cách giữa 2 khung: thường ${q(0.5)} ms · 95% dưới ${q(0.95)} ms · lâu nhất ${gaps.length ? gaps[gaps.length - 1] : 0} ms`);
  console.log(`Dung lượng: ${(bytes * 8 / SEC / 1e6).toFixed(2)} Mbps`);
  process.exit(0);
}, SEC * 1000);
