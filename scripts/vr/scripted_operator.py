"""A scripted "operator" that drives the VR collector without a headset (smoke tests only).

It plays the person holding the Touch controllers: each control step it emits a WebXR report (the
exact format the headset page sends, controller poses in WebXR axes) and lets the real pipeline do
the rest (WebSocket -> vr_teleop clutch/recenter/buttons -> absolute IK -> recording -> success).

T1 (left arm): Y held (recenter) -> A (start recording) -> grip held: pinch the bowl rim nearest the
robot with the READY gripper orientation (as keyboard operators do), lift, carry over the plate,
place, open, back to the start pose. Halfway it lets go of grip, moves the "hand" elsewhere and grabs
again, to exercise the clutch re-anchoring.
"""

import math

import numpy as np

from vr_teleop import XR_TO_ROBOT, mat_to_quat, rot_z

RIM_OFFSET = np.array([-0.085, 0.0, 0.0])  # rim point nearest the robot, from the bowl centre
PINCH_DEPTH = 0.02  # below the rim top (T1 bowl, 8.2 cm tall)
SPEED = 0.10  # m per simulated second of the scripted hand


def to_xr(p, R):
    return XR_TO_ROBOT.T @ p, XR_TO_ROBOT.T @ R @ XR_TO_ROBOT


def controller(p, R, squeeze=0.0, trigger=0.0, lower=0.0, upper=0.0):
    pxr, Rxr = to_xr(p, R)
    return {"profile": "scripted", "tracked": True, "hand_tracking": False,
            "position": pxr.tolist(), "orientation": mat_to_quat(Rxr).tolist(),
            "buttons": [trigger, squeeze, 0.0, 0.0, lower, upper, 0.0], "axes": [0.0] * 4}


class T1Operator:
    def __init__(self, fps):
        self.dt = 1.0 / fps
        self.phase = "recenter"
        self.t_phase = None  # wall time the phase started (button holds)
        self.wait = 0  # control steps left to wait
        self.squeeze = 0.0
        self.trigger = 0.0
        self.anchor = None  # (C0, E0) at the last grip press, mirrors the clutch
        self.hand = {"left": (np.array([-0.1, 0.25, 0.95]), np.eye(3)), "right": (np.array([-0.1, -0.25, 0.95]), np.eye(3))}
        self.plan = []
        self.log = []
        self.settle = 0

    def _press_grip(self, current):
        self.squeeze = 1.0
        self.anchor = (self.hand["left"], current)

    def _set_desired(self, p, R):
        """Move the virtual left controller so the clutch maps it onto the desired gripper pose."""
        (pc0, Rc0), (pe0, Re0) = self.anchor
        self.hand["left"] = (pc0 + (p - pe0), R @ Re0.T @ Rc0)

    def step(self, wall, current, measured, bowl, plate):
        """current: commanded left gripper pose (p, R) (what the clutch anchors on); measured: TCP position
        from the measured joints; bowl/plate: centres in the robot frame (bowl[3] = rim top z).
        Returns the WebXR report for this control step."""
        lower = upper = 0.0
        if self.t_phase is None:
            self.t_phase = wall
        if self.phase == "recenter":  # Y held >= 1 s (see the hands below)
            if wall - self.t_phase > 1.3:
                self.phase, self.t_phase = "start", wall
        if self.phase == "start":
            lower = 1.0  # A for one step
            self.phase = "plan"
        elif self.phase == "plan":
            p0, R0 = current
            top = bowl[3]
            g = np.array([bowl[0], bowl[1], top - PINCH_DEPTH]) + RIM_OFFSET
            pl = np.array([plate[0], plate[1], top - PINCH_DEPTH + 0.025]) + RIM_OFFSET
            up = np.array([0, 0, 1.0])
            self.plan = [("pregrasp", g + 0.10 * up), ("grasp", g), ("close", None), ("lift", g + 0.12 * up),
                         ("regrip", None), ("preplace", pl + 0.10 * up), ("place", pl), ("open", None),
                         ("release_up", pl + 0.10 * up), ("home", p0)]
            self.R = R0
            self.desired = p0.copy()
            self._press_grip(current)
            self.phase = "run"
        elif self.phase == "run" and self.wait > 0:
            self.wait -= 1
        elif self.phase == "run" and self.plan:
            name, goal = self.plan[0]
            if name == "close":
                self.trigger, self.wait = 1.0, int(1.5 / self.dt)
                self.plan.pop(0)
            elif name == "open":
                self.trigger, self.wait = 0.0, int(1.0 / self.dt)
                self.plan.pop(0)
            elif name == "regrip":  # let go, move the hand 20 cm aside and down, grab again
                if self.squeeze:
                    self.squeeze, self.wait = 0.0, 2
                    p, R = self.hand["left"]
                    self.hand["left"] = (p + np.array([-0.2, 0.1, -0.15]), rot_z(0.4) @ R)
                else:
                    self._press_grip(current)
                    self.plan.pop(0)
            else:
                d = goal - self.desired
                n = np.linalg.norm(d)
                self.desired = goal.copy() if n <= SPEED * self.dt else self.desired + d / n * SPEED * self.dt
                if n <= SPEED * self.dt:
                    err = float(np.linalg.norm(measured - goal))
                    if err < 0.01 or self.settle > int(3.0 / self.dt):
                        self.log.append((name, round(err, 4)))
                        self.plan.pop(0)
                        self.settle = 0
                    else:
                        self.settle += 1
                if self.squeeze:
                    self._set_desired(self.desired, self.R)
        elif self.phase == "run":
            self.phase = "done"
            self.squeeze = 0.0
        hands = {
            "left": controller(*self.hand["left"], squeeze=self.squeeze, trigger=self.trigger,
                               upper=1.0 if self.phase == "recenter" else 0.0),
            "right": controller(*self.hand["right"], lower=lower),
        }
        return {"kind": "frame", "fps": 90.0, "hands": hands,
                "head": {"position": [0.0, 1.2, 0.0], "orientation": [1.0, 0.0, 0.0, 0.0]}}


class InputReplay:
    """Replays headset reports recorded with --vr-record (smoke runs): the operator's real hand motion,
    buttons and head pose, re-timed to simulated time so a headless run reproduces the session."""

    def __init__(self, path, session=-1):
        import json

        rows = [json.loads(line) for line in open(path)]
        starts = [i for i, r in enumerate(rows) if r.get("kind") == "hello"] or [0]
        start = starts[session]
        end = starts[starts.index(start) + 1] if start != starts[-1] else len(rows)
        self.frames = [r for r in rows[start:end] if r.get("kind") == "frame"]
        if not self.frames:
            raise ValueError(f"no headset frames in page session {session} of {path}")
        t0 = self.frames[0]["recv_t"]
        self.times = [r["recv_t"] - t0 for r in self.frames]
        self.i = 0
        self.duration = self.times[-1]
        self.log = []

    def step(self, t):
        """Newest recorded report at replay time t (s), or None when the recording is over."""
        if t > self.duration:
            return None
        while self.i + 1 < len(self.times) and self.times[self.i + 1] <= t:
            self.i += 1
        r = dict(self.frames[self.i])
        r.pop("recv_t", None)
        return r
