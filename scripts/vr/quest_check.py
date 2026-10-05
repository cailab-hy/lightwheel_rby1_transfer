"""Stage-1 check for Meta Quest 2 + WebXR, without Vuer or internet access.

Serves a small WebXR page on http://localhost:PORT (reach it from the headset through
`adb reverse tcp:PORT tcp:PORT`; localhost counts as a secure context, so WebXR works over
plain HTTP). After "Enter VR", the page posts both controllers' poses and button states to
this server, which prints them, so this also proves the headset -> PC data path.

  ./scripts/vr/quest_check.sh            # adb checks + reverse + this server
  ./scripts/vr/quest_check.sh --teleop   # also print vr_teleop output (robot-frame targets)
  ./scripts/vr/quest_check.sh --teleop --record ~/quest_check_raw.jsonl   # also save raw reports
  python3 scripts/vr/quest_check.py 8012  # server only
"""
import argparse, json, math, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("port", nargs="?", type=int, default=8012)
ap.add_argument("--teleop", action="store_true", help="run vr_teleop on the reports and print its output")
ap.add_argument("--motion-scale", type=float, default=1.0)
ap.add_argument("--record", metavar="JSONL", help="append every report (with PC receive time) to this file")
args = ap.parse_args()
PORT = args.port

PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RB-Y1 Quest check</title>
<style>body{font:20px sans-serif;margin:24px;background:#111;color:#eee}button{font-size:28px;padding:16px 32px}
.ok{color:#6f6}.bad{color:#f66}pre{font-size:16px}</style></head><body>
<h2>RB-Y1 Quest 2 WebXR check</h2>
<div id="env"></div><p><button id="enter" disabled>Enter VR</button></p><pre id="log"></pre>
<script>
const PAGE_VERSION = 2;
const env = document.getElementById('env'), log = document.getElementById('log'), btn = document.getElementById('enter');
function line(label, ok, extra) { env.innerHTML += `<div>${label}: <b class="${ok ? 'ok' : 'bad'}">${ok ? 'OK' : 'NO'}</b> ${extra || ''}</div>`; }
function post(kind, data) { fetch('/report', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({kind, v: PAGE_VERSION, t: performance.now(), ...data})}).catch(() => {}); }
line('secure context (localhost or https)', window.isSecureContext, location.origin);
line('navigator.xr', !!navigator.xr);
post('hello', {secure: window.isSecureContext, xr: !!navigator.xr, ua: navigator.userAgent});
if (navigator.xr) navigator.xr.isSessionSupported('immersive-vr').then(ok => {
  line('immersive-vr supported', ok); btn.disabled = !ok; post('support', {immersive_vr: ok});
});
btn.onclick = async () => {
  const session = await navigator.xr.requestSession('immersive-vr', {optionalFeatures: ['local-floor']});
  const canvas = document.createElement('canvas'), gl = canvas.getContext('webgl', {xrCompatible: true});
  session.updateRenderState({baseLayer: new XRWebGLLayer(session, gl)});
  let space; try { space = await session.requestReferenceSpace('local-floor'); } catch (e) { space = await session.requestReferenceSpace('local'); }
  post('session', {started: true});
  let last = 0, frames = 0;
  session.addEventListener('end', () => post('session', {started: false}));
  session.requestAnimationFrame(function onFrame(t, frame) {
    session.requestAnimationFrame(onFrame); frames++;
    const layer = session.renderState.baseLayer;
    gl.bindFramebuffer(gl.FRAMEBUFFER, layer.framebuffer); gl.clearColor(0.05, 0.08, 0.12, 1); gl.clear(gl.COLOR_BUFFER_BIT);
    if (t - last < 100) return;                        // ~10 reports per second
    const hands = {};
    for (const src of session.inputSources) {
      const pose = src.gripSpace && frame.getPose(src.gripSpace, space);
      const gp = src.gamepad;
      hands[src.handedness] = {
        profile: (src.profiles || [])[0] || '', tracked: !!pose, hand_tracking: !!src.hand,
        position: pose ? [pose.transform.position.x, pose.transform.position.y, pose.transform.position.z] : null,
        orientation: pose ? [pose.transform.orientation.w, pose.transform.orientation.x, pose.transform.orientation.y, pose.transform.orientation.z] : null,
        buttons: gp ? gp.buttons.map(b => Math.round(b.value * 100) / 100) : [], axes: gp ? Array.from(gp.axes, a => Math.round(a * 100) / 100) : []
      };
    }
    const viewer = frame.getViewerPose(space);
    post('frame', {fps: frames * 1000 / (t - last), hands, head: viewer ? {position: [viewer.transform.position.x, viewer.transform.position.y, viewer.transform.position.z],
                      orientation: [viewer.transform.orientation.w, viewer.transform.orientation.x, viewer.transform.orientation.y, viewer.transform.orientation.z]} : null});
    frames = 0; last = t;
  });
};
</script></body></html>"""

record = open(Path(args.record).expanduser(), "a") if args.record else None
record_lock = threading.Lock()
PAGE_VERSION = 2  # keep in sync with the page; an older open tab is detected and reported
state = {"reports": 0, "t0": time.time(), "m0": time.monotonic()}

if args.teleop:
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from vr_teleop import SIDES, VRTeleop

    # page reports arrive at ~10 Hz over HTTP here, so allow 0.5 s before treating input as stale
    teleop = VRTeleop(scale=args.motion_scale, stale_s=0.5)
    ee = {s: (np.zeros(3), np.eye(3)) for s in SIDES}  # stand-in arm targets, start at the origin
    lock = threading.Lock()
    NAMES = {"left": {0: "trigger", 1: "grip", 3: "stick-click", 4: "X", 5: "Y"},
             "right": {0: "trigger", 1: "grip", 3: "stick-click", 4: "A", 5: "B"}}
    AXES = ("forward(+x)", "left(+y)", "up(+z)")
    mem = {s: {"seen": None, "track": None, "down": {}, "gripper": False, "clutch": None} for s in SIDES}
    mem["beat"] = 0.0

    def rotvec(R):
        angle = math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))
        if angle < 1e-6:
            return np.zeros(3)
        axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * math.sin(angle))
        return axis * angle

    def describe_move(dp, dR):
        i = int(np.argmax(np.abs(dp)))
        move = f"mostly {'+' if dp[i] > 0 else '-'}{AXES[i].split('(')[0]}" if np.linalg.norm(dp) > 0.02 else "barely moved (<2 cm)"
        rv = np.degrees(rotvec(dR))
        j = int(np.argmax(np.abs(rv)))
        turn = (f"turned {np.linalg.norm(rv):.0f} deg mostly about {'+' if rv[j] > 0 else '-'}{'xyz'[j]}"
                f" ({['roll', 'pitch', 'yaw'][j]})") if np.linalg.norm(rv) > 10 else "no big turn (<10 deg)"
        return (f"dxyz(m)={dp[0]:+.3f},{dp[1]:+.3f},{dp[2]:+.3f} -> {move};  "
                f"rot(deg about x,y,z)={rv[0]:+.0f},{rv[1]:+.0f},{rv[2]:+.0f} -> {turn}")

    def say(msg):
        print(f"{time.monotonic() - state['m0']:7.1f}s  {msg}", flush=True)

    def teleop_step(data):
        now = data["recv_t"] = time.monotonic()
        with lock:
            step = teleop.update(data, now, ee)
            for side in SIDES:
                if step.targets[side] is not None:
                    ee[side] = step.targets[side]
        for name in step.events:
            if name == "recenter" and not (isinstance(data.get("head"), dict) and data["head"].get("orientation")):
                say(">>> event: recenter IGNORED - no head orientation (old page: reload it in the headset)")
                continue
            say(f">>> event: {name}" + (f"  (operator heading {math.degrees(teleop.yaw):+.0f} deg is now robot +x)" if name == "recenter" else ""))
        hands = data.get("hands", {})
        for side in ("left", "right"):
            m, st, h = mem[side], step.status[side], hands.get(side) or {}
            seen = (h.get("profile"), len(h.get("buttons") or []), len(h.get("axes") or []))
            if h and seen != m["seen"]:
                m["seen"] = seen
                say(f"[{side}] controller profile={seen[0]!r}, {seen[1]} buttons, {seen[2]} axes")
            track = "ok" if st["tracked"] else st["reason"]
            if track != m["track"]:
                m["track"] = track
                say(f"[{side}] tracking: {track}")
            for i, v in enumerate(h.get("buttons") or []):
                d = m["down"].get(i)
                if v > 0.5 and d is None:
                    m["down"][i] = [now, v]
                    say(f"[{side}] {NAMES[side].get(i, f'button {i}')} pressed ({v:.2f})")
                elif d is not None and v > 0.5:
                    d[1] = max(d[1], v)
                elif d is not None and v < 0.3:
                    m["down"].pop(i)
                    say(f"[{side}] {NAMES[side].get(i, f'button {i}')} released (held {now - d[0]:.1f} s, peak {d[1]:.2f})")
            if step.gripper_closed[side] != m["gripper"]:
                m["gripper"] = step.gripper_closed[side]
                say(f"[{side}] gripper {'CLOSED' if m['gripper'] else 'open'} (trigger {st['trigger']:.2f})")
            if st["engaged"] and m["clutch"] is None:
                m["clutch"] = (now, ee[side][0].copy(), ee[side][1].copy())
                say(f"[{side}] CLUTCH on  - arm follows the controller")
            elif not st["engaged"] and m["clutch"] is not None:
                t0, p0, R0 = m["clutch"]
                m["clutch"] = None
                say(f"[{side}] CLUTCH off after {now - t0:.1f} s: " + describe_move(ee[side][0] - p0, ee[side][1] @ R0.T))
            elif st["engaged"] and state["reports"] % 5 == 0:
                t0, p0, R0 = m["clutch"]
                dp = ee[side][0] - p0
                say(f"[{side}]   ... dxyz={dp[0]:+.3f},{dp[1]:+.3f},{dp[2]:+.3f}")
        if now - mem["beat"] > 5:
            mem["beat"] = now
            say("status  " + "  |  ".join(
                f"{side}: {'GRIP' if step.status[side]['engaged'] else mem[side]['track']}, "
                f"gripper {'CLOSED' if step.gripper_closed[side] else 'open'}" for side in ("left", "right")))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        self.send_response(204); self.end_headers()
        kind = data.get("kind")
        if record:
            with record_lock:
                record.write(json.dumps({"recv_t": time.monotonic(), **data}) + "\n")
                record.flush()
        if kind == "hello":
            print(f"[page] connected  secure_context={data.get('secure')}  navigator.xr={data.get('xr')}\n       {data.get('ua')}", flush=True)
        elif kind == "support":
            print(f"[page] immersive-vr supported: {data.get('immersive_vr')}", flush=True)
        elif kind == "session":
            print(f"[page] VR session {'started' if data.get('started') else 'ended'}", flush=True)
        elif kind == "frame":
            state["reports"] += 1
            if data.get("v") != PAGE_VERSION and not state.get("warned"):
                state["warned"] = True
                print("!!! The headset is running an old copy of this page. In the headset: exit VR, press the browser's "
                      "reload button (or reopen http://localhost:%d), then Enter VR again." % PORT, flush=True)
            if args.teleop:
                teleop_step(data)
            elif state["reports"] % 5 == 1:   # print ~2x per second
                parts = [f"xr {data.get('fps', 0):5.1f} fps"]
                for side in ("left", "right"):
                    h = data.get("hands", {}).get(side)
                    if not h:
                        parts.append(f"{side}: --"); continue
                    p = h["position"]
                    pressed = [i for i, v in enumerate(h["buttons"]) if v > 0.5]
                    parts.append(f"{side}: {'tracked' if h['tracked'] else 'LOST'}{' (HAND!)' if h['hand_tracking'] else ''} "
                                 f"pos={'%+.3f,%+.3f,%+.3f' % tuple(p) if p else '-'} trig={h['buttons'][0] if h['buttons'] else '-'} "
                                 f"grip={h['buttons'][1] if len(h['buttons']) > 1 else '-'} pressed={pressed} stick={h['axes'][2:4] if len(h['axes']) >= 4 else h['axes']}")
                print("  |  ".join(parts), flush=True)


print(f"Quest check server on http://localhost:{PORT}  (Ctrl+C to stop)", flush=True)
try:
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
except KeyboardInterrupt:
    print("\nstopped" + (f"; raw reports saved to {args.record}" if args.record else ""), flush=True)
