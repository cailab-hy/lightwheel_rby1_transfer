"""Scripted oracle for T1-T10: Cartesian waypoints from ground-truth simulator state.

Each task is a fixed sequence of sub-motions (approach -> pre-grasp -> grasp -> lift -> carry
-> place -> release -> retreat, or handle approach -> pull / turn / push). Waypoints are computed
from the true object, handle and drawer poses at the moment a sub-motion starts. The tool centre
point (TCP, finger mid-depth) follows smooth straight-line paths; the environment turns them into
joint targets with the collector's absolute Differential IK.

No recovery: there is no re-grasp, no noise and no retry. If a sub-motion does not reach its goal
the plan simply continues, and the attempt is discarded when success_original never latches.
The oracle has no random numbers; the layout seed alone determines the attempt.

TCP frame (kinematics.build_rby): x = finger closing axis, z = back toward the wrist, so the
fingers point along -z ("approach" direction).
"""
import math
import os

import numpy as np
import pinocchio as pin

from sim_env import FPS

UP = np.array([0.0, 0.0, 1.0])


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def frame(approach, close):
    """Rotation whose -z is `approach` and whose x is `close` (orthogonalised)."""
    z = -unit(approach)
    x = np.asarray(close, dtype=float) - np.dot(close, z) * z
    x = unit(x)
    return np.column_stack([x, np.cross(z, x), z])


def rot_about(axis, angle):
    return pin.exp3(unit(axis) * angle)


def smooth(t):
    return t * t * (3 - 2 * t)


class Oracle:
    def __init__(self, env):
        self.env = env
        self.task = env.task
        self.desired = {s: env.target_pose(s) for s in ["left", "right"]}
        self.active = {"left": False, "right": False}
        self.joint_goal = {"left": None, "right": None}  # set during joint-space moves
        self.stage = "start"
        self.last_delta = np.zeros(6)
        self.last_side = "left"
        self.plan = PLANS[self.task](self)
        self.done = False
        self.notes = {}
        self.log = []  # (stage, final position error m, rotation error rad) of each move

    # -------------------------------------------------------------- per-step interface
    def step(self):
        """Advance one control step; returns {side: (p, R) or None}."""
        before = {s: (self.desired[s][0].copy(), self.desired[s][1].copy()) for s in self.desired}
        if not self.done:
            try:
                next(self.plan)
            except StopIteration:
                self.done = True
                self.stage = "hold"
        self.last_delta = np.zeros(6)
        for s in ["left", "right"]:
            dp = self.desired[s][0] - before[s][0]
            dr = pin.log3(before[s][1].T @ self.desired[s][1])
            if np.linalg.norm(dp) > 1e-9 or np.linalg.norm(dr) > 1e-9:
                self.last_delta = np.r_[dp, before[s][1] @ dr]
                self.last_side = s
        return {s: ({"joints": self.joint_goal[s]} if self.joint_goal[s] is not None
                    else self.desired[s] if self.active[s] else None) for s in ["left", "right"]}

    def command_vector(self):
        """teleop.command row: commanded TCP delta of the moving arm, arm flag, its gripper state."""
        s = self.last_side
        return np.r_[self.last_delta, float(s == "right"), float(self.env.grip_open[s])].astype(np.float32)

    # -------------------------------------------------------------- measurements
    def tcp(self, side):
        return self.env.tcp(side)

    # -------------------------------------------------------------- skills (generators, one yield per step)
    def move(self, side, p, R=None, speed=0.12, wspeed=0.9, tol=0.012, settle=1.0, stage=None):
        """Straight-line TCP move with a smooth (cubic) time profile, then wait for the arm to arrive."""
        if stage:
            self.stage = stage
        self.last_side = side
        self.active[side] = True
        p0, R0 = self.desired[side]
        p = np.asarray(p, dtype=float)
        R = R0 if R is None else R
        w = pin.log3(R0.T @ R)
        dist, ang = np.linalg.norm(p - p0), np.linalg.norm(w)
        n = max(1, int(math.ceil(max(dist / speed, ang / wspeed) * FPS)))
        for k in range(1, n + 1):
            s = smooth(k / n)
            self.desired[side] = (p0 + s * (p - p0), R0 @ pin.exp3(s * w))
            yield
        for _ in range(int(settle * FPS)):
            if np.linalg.norm(self.tcp(side)[0] - p) < tol:
                break
            yield
        pm, Rm = self.tcp(side)
        joints = [round(float(v), 3) for k in self.env.success.arts for v in self.env.fixture_joints(k).values() if abs(v) > 1e-3]
        self.log.append((self.stage, round(float(np.linalg.norm(pm - p)), 4), round(float(np.linalg.norm(pin.log3(Rm.T @ R))), 3), joints))

    def moves(self, *gens):
        """Run several move generators in lock-step (e.g. both arms)."""
        gens = list(gens)
        while gens:
            alive = []
            for g in gens:
                try:
                    next(g)
                    alive.append(g)
                except StopIteration:
                    pass
            gens = alive
            if gens:
                yield

    def grip(self, side, close, secs=1.0, stage=None):
        if stage:
            self.stage = stage
        self.env.grip_open[side] = not close
        for _ in range(int(secs * FPS)):
            yield

    def wait(self, secs):
        for _ in range(int(secs * FPS)):
            yield

    def home(self, side, stage="retreat", speed=0.15, **kw):
        p, R = self.env.home_pose[side]
        yield from self.move(side, p, R, speed=speed, stage=stage, **kw)

    def joint_home(self, side, speed=0.6, stage="retreat", settle=0.5):
        """Return to READY along a straight line in joint space, commanding the arm joints directly
        (smooth profile, `speed` rad/s for the joint that moves most). For returns where the IK
        path would swing the arm through the body or get stuck near joint limits."""
        self.stage = stage
        self.last_side = side
        self.active[side] = True
        ids = self.env.arms[side]
        q0, q1 = self.env.target[ids].copy(), self.env.ready[ids].copy()
        n = max(1, int(math.ceil(np.abs(q1 - q0).max() / speed * FPS)))
        for k in range(1, n + 1):
            self.joint_goal[side] = q0 + smooth(k / n) * (q1 - q0)
            self.desired[side] = self.pose_at(side, self.joint_goal[side])
            yield
        for _ in range(int(settle * FPS)):
            yield
        self.joint_goal[side] = None
        p, R = self.env.home_pose[side]
        self.desired[side] = (p, R)
        pm, Rm = self.tcp(side)
        self.log.append((self.stage, round(float(np.linalg.norm(pm - p)), 4), round(float(np.linalg.norm(pin.log3(Rm.T @ R))), 3), []))

    def pose_at(self, side, arm_q):
        """TCP pose with the arm at `arm_q` (other joints at the current target), computed on a
        separate pinocchio Data so the Jacobians env.action() uses this step stay intact."""
        m = self.env.model
        if not hasattr(self, "_fk_data"):
            self._fk_data = m.model.createData()
        q = self.env.target.copy()
        q[self.env.arms[side]] = arm_q
        pin.framesForwardKinematics(m.model, self._fk_data, m.q_from_dict(dict(zip(self.env.names, q))))
        t = self._fk_data.oMf[m.frame[side]]
        return t.translation.copy(), t.rotation.copy()

    # -------------------------------------------------------------- helpers
    def carry_offset(self, side, name):
        """Object centre minus TCP position (robot frame) while the object is held."""
        return self.env.object_center(name)[:3] - self.tcp(side)[0]


# ====================================================================== task plans
# Gripper orientations are built from the READY orientation (fingers closing along robot x,
# pointing down and inward) because that is where the arms have the most reach near the table.

def ready_R(o, side):
    return o.env.home_pose[side][1]


def pinch_rim_plan(o, side, obj, rest, rim=0.085, depth=0.02, lift=0.12, clearance=0.10,
                   place_dz=0.01, R=None, stage_prefix="", release_back=0.0):
    """Pinch the rim nearest the robot (fingers across the rim wall), lift, carry so the object
    centre ends above `rest` (its resting centre position), lower and release."""
    R = ready_R(o, side) if R is None else R
    c = o.env.object_center(obj)
    g = np.array([c[0] - rim, c[1], c[3] - depth])
    yield from o.move(side, g + clearance * UP, R, stage=stage_prefix + "approach")
    yield from o.move(side, g, R, speed=0.06, tol=0.005, settle=1.5, stage=stage_prefix + "pregrasp")
    yield from o.grip(side, True, 1.2, stage=stage_prefix + "grasp")
    yield from o.move(side, g + lift * UP, R, speed=0.08, stage=stage_prefix + "lift")
    yield from place_held(o, side, obj, rest, R, clearance, place_dz, stage_prefix, release_back=release_back)


def place_held(o, side, obj, rest, R, clearance=0.10, place_dz=0.01, stage_prefix="", release_up=0.10, release_back=0.0):
    """Carry the held object so its centre goes to `rest` (+place_dz), release, move up."""
    off = o.carry_offset(side, obj)
    drop = np.asarray(rest, dtype=float) - off + place_dz * UP
    p_now = o.desired[side][0]
    z = max(p_now[2], drop[2] + clearance)
    if z > p_now[2] + 0.005:  # rise first so the carry does not sweep through fixtures
        yield from o.move(side, np.array([p_now[0], p_now[1], z]), R, speed=0.08, settle=0.3, stage=stage_prefix + "lift")
    yield from o.move(side, np.array([drop[0], drop[1], z]), R, stage=stage_prefix + "carry")
    yield from o.move(side, drop, R, speed=0.05, stage=stage_prefix + "place")
    yield from o.grip(side, False, 1.0, stage=stage_prefix + "release")
    yield from o.move(side, drop + release_up * UP - np.array([release_back, 0.0, 0.0]), R, speed=0.08, stage=stage_prefix + "release_up")


def size_of(o, name):
    e = next(x for x in o.env.meta["objects"] if x["name"] == name)
    return np.asarray(e["aabb"][1]) - np.asarray(e["aabb"][0])


def nearest_yaw(o, side, Rs):
    """Of several equivalent gripper rotations pick the one closest to the current command."""
    R0 = o.desired[side][1]
    return min(Rs, key=lambda R: np.linalg.norm(pin.log3(R0.T @ R)))


def camera_up(side, Rs):
    """Of equivalent gripper rotations pick the one with the wrist D405 mount on top (it sits on
    ee +y of the left hand and -y of the right one and hangs 2.3 cm below the palm)."""
    d = np.array([0.0, 1.0 if side == "left" else -1.0, 0.0])
    return max(Rs, key=lambda R: (R @ d)[2])


def vertical_mount_clear(o, side, close, hand_xy, keep_out_xy, keep_out_r):
    """vertical(), unless the D405 mount (8.9 cm to one side of a vertical hand) would reach over
    a keep-out disc (e.g. a basket next to the grasped object); then the hand turned by 180 deg.
    Only flip when needed: the flipped hand puts the arm on another wrist branch."""
    d = np.array([0.0, 1.0 if side == "left" else -1.0, 0.0])
    R = vertical(o, side, close)
    tip = np.asarray(hand_xy)[:2] + 0.089 * (R @ d)[:2]
    if np.linalg.norm(tip - np.asarray(keep_out_xy)[:2]) < keep_out_r:
        R = frame(-UP, -R[:, 0])
    return R


def vertical(o, side, close):
    close = unit(close)
    return nearest_yaw(o, side, [frame(-UP, close), frame(-UP, -close)])


def grasp_top(o, side, obj, R, depth=0.025, clearance=0.10, lift_to=None, stage_prefix=""):
    """Top-down pinch of an upright object (cans, bottle): TCP `depth` below its top, lift."""
    c = o.env.object_center(obj)
    g = np.array([c[0], c[1], c[3] - depth])
    yield from o.move(side, g + clearance * UP, R, stage=stage_prefix + "approach")
    yield from o.move(side, g, R, speed=0.06, tol=0.005, settle=1.5, stage=stage_prefix + "pregrasp")
    yield from o.grip(side, True, 1.2, stage=stage_prefix + "grasp")
    top = g[2] + clearance if lift_to is None else lift_to
    yield from o.move(side, np.array([g[0], g[1], top]), R, speed=0.08, stage=stage_prefix + "lift")


def plan_T1(o):
    plate = o.env.object_center("plate")
    bowl = o.env.object_center("bowl")
    # resting bowl centre on the plate: plate top + the bowl's centre height above its support
    rest = np.array([plate[0], plate[1], plate[3] + (bowl[3] - bowl[2])])
    # Vertical hand: the READY hand is tilted ~40 deg, which drops the palm's edge to TCP height and
    # into the rim; vertical, the palm is 3.2 cm and the D405 mount 2.3 cm above the TCP.
    yield from pinch_rim_plan(o, "left", "bowl", rest, depth=0.012, R=vertical(o, "left", [1.0, 0.0, 0.0]))
    yield from o.home("left")


def plan_T2(o):
    plate = o.env.object_center("plate")
    bowl = o.env.object_center("bowl")
    rim = size_of(o, "bowl")[0] / 2 - 0.006
    rest = np.array([plate[0], plate[1], plate[3] + (bowl[3] - bowl[2])])
    yield from pinch_rim_plan(o, "left", "bowl", rest, rim=rim, depth=0.003)
    yield from o.home("left")


def basket_drop(o, side, obj, basket, R, dy=0.0, stage_prefix=""):
    """Held object above the basket centre (bottom clear of the rim), lower inside, release."""
    off = o.carry_offset(side, obj)
    half = (size_of(o, obj)[2]) / 2
    rim_top = basket[3]
    centre = np.array([basket[0], basket[1] + dy, 0.0])
    above = centre - np.r_[off[:2], 0.0] + np.array([0, 0, rim_top + half + 0.04 - off[2]])
    yield from o.move(side, np.r_[above[:2], max(o.desired[side][0][2], above[2])], R, stage=stage_prefix + "carry")
    inside = above.copy()
    inside[2] = basket[2] - (basket[3] - basket[2]) + 0.05 + half - off[2]  # bottom ~5 cm above the basket floor
    # but keep the gripper body out of the narrow basket (its lowest part, the D405 mount of the
    # vertical hand, 2 cm above the rim): lowered inside, the hand wedged and lifted the basket
    inside[2] = max(inside[2], rim_top + 0.02 - 0.0226)
    yield from o.move(side, inside, R, speed=0.06, stage=stage_prefix + "place")
    yield from o.grip(side, False, 1.0, stage=stage_prefix + "release")
    yield from o.move(side, np.r_[inside[:2], rim_top + 0.12], R, speed=0.08, stage=stage_prefix + "release_up")


def vertical_retreat(o, side, R, stage="retreat"):
    """From a vertical hand: back over the hand's own side, still vertical and above its READY
    height, then turn to READY in joint space. Turning on the way (IK) lifted the right elbow into
    the head and torso; a joint-space line straight from the basket dipped the hand into its rim."""
    home_p = o.env.home_pose[side][0]
    yield from o.move(side, np.r_[home_p[:2], max(o.desired[side][0][2], home_p[2] + 0.05)], R, stage=stage)
    yield from o.joint_home(side, stage=stage)


def plan_T3(o):
    side = "left"
    obj = "ketchup"
    _, Rk = o.env.object_pose(o.env.success_key(obj))
    narrow = Rk[:, 1] if size_of(o, obj)[1] < size_of(o, obj)[0] else Rk[:, 0]
    basket = o.env.object_center("basket")
    R = vertical_mount_clear(o, side, np.r_[narrow[:2], 0.0], o.env.object_center(obj), basket,
                             size_of(o, "basket")[:2].max() / 2 + 0.01)
    yield from grasp_top(o, side, obj, R, depth=0.03, lift_to=basket[3] + size_of(o, obj)[2] + 0.06)
    yield from basket_drop(o, side, obj, basket, R)
    yield from o.home(side)


def plan_T10(o):
    for side, obj, dy in [("left", "alphabet_soup", 0.035), ("right", "tomato_sauce", -0.035)]:
        basket = o.env.object_center("basket")  # re-read: the first can may have moved the basket
        R = vertical(o, side, [1.0, 0.0, 0.0])
        yield from grasp_top(o, side, obj, R, depth=0.03, lift_to=basket[3] + size_of(o, obj)[2] + 0.06, stage_prefix=f"{obj}:")
        yield from basket_drop(o, side, obj, basket, R, dy=dy, stage_prefix=f"{obj}:")
        yield from vertical_retreat(o, side, R, stage=f"{obj}:retreat")


def plan_T8(o):
    back = o.env.object_center("back_bowl")
    mid = o.env.object_center("middle_bowl")
    rim = size_of(o, "middle_bowl")[0] / 2 - 0.006
    rest = np.array([back[0], back[1], back[3] + 0.5 * (mid[3] - mid[2])])
    # vertical hand: with the tilted READY hand the palm edge hits the rim (see plan_T1)
    yield from pinch_rim_plan(o, "left", "middle_bowl", rest, rim=rim, depth=0.012, place_dz=0.015,
                              R=vertical(o, "left", [1.0, 0.0, 0.0]))
    yield from o.home("left")


def plan_T6(o):
    side = "left"
    knob = o.env.knob_center()
    R = vertical(o, side, [0.0, 1.0, 0.0])
    g = np.array([knob[0], knob[1], knob[2] + 0.031 - 0.012])
    yield from o.move(side, g + 0.10 * UP, R, stage="approach")
    yield from o.move(side, g, R, speed=0.05, tol=0.005, settle=1.5, stage="pregrasp")
    yield from o.grip(side, True, 1.0, stage="grasp")
    yield from o.move(side, g, rot_about(UP, KNOB_TURN) @ R, wspeed=0.6, stage="turn")
    yield from o.grip(side, False, 0.8, stage="release")
    yield from o.move(side, g + 0.10 * UP, stage="release_up")
    yield from o.home(side)


KNOB_TURN = 0.9  # rad about +z; sign set from the T6 knob joint (opening direction)


def bar_grasp_frame(o, side, beta, gamma):
    """Grasp of a horizontal bar along robot y: fingers close across the bar along c = (sin b, 0, cos b)
    (b = tilt of the closing axis from vertical toward +x); the approach is perpendicular to c,
    pitched forward-down and turned by g toward the arm's own side (from outside the bar).
    Chosen with an offline kinematic search: reachable with >= 0.4 rad joint-limit margin."""
    c = np.array([np.sin(beta), 0.0, np.cos(beta)])
    inward = -1.0 if side == "left" else 1.0
    a = np.cos(gamma) * np.array([np.cos(beta), 0.0, -np.sin(beta)]) + np.sin(gamma) * np.array([0.0, inward, 0.0])
    return a, nearest_yaw(o, side, [frame(a, c), frame(a, -c)])


BAR_BETA = float(os.environ.get("ORACLE_BAR_BETA", 60))
BAR_GAMMA = float(os.environ.get("ORACLE_BAR_GAMMA", 40))
BAR_XSHIFT = float(os.environ.get("ORACLE_BAR_XSHIFT", -0.008))


def pull_drawer(o, side, drawer_body, pull=0.14, side_shift=-0.01, beta=None, gamma=None, stage_prefix=""):
    """Grasp the horizontal drawer handle bar and pull straight back (-x)."""
    h = o.env.handle_point(drawer_body) + np.array([BAR_XSHIFT, side_shift if side == "left" else -side_shift, 0.0])
    a, R = bar_grasp_frame(o, side, np.radians(BAR_BETA if beta is None else beta), np.radians(BAR_GAMMA if gamma is None else gamma))
    g = h
    yield from o.move(side, g - 0.10 * a + 0.02 * UP, R, stage=stage_prefix + "approach")
    yield from o.move(side, g, R, speed=0.05, tol=0.005, settle=1.5, stage=stage_prefix + "pregrasp")
    yield from o.grip(side, True, 1.0, stage=stage_prefix + "grasp")
    yield from o.move(side, g - np.array([pull, 0.0, 0.0]), R, speed=0.06, stage=stage_prefix + "pull")
    yield from o.grip(side, False, 0.8, stage=stage_prefix + "release")
    p = o.desired[side][0]
    # lift the rear finger straight out of the gap behind the bar before backing away
    yield from o.move(side, p + 0.06 * UP, R, speed=0.05, stage=stage_prefix + "release_up")
    yield from o.move(side, p + 0.06 * UP - 0.06 * np.r_[a[:2], 0.0], R, speed=0.08, stage=stage_prefix + "release_back")


def plan_T4(o):
    yield from pull_drawer(o, "left", "Drawer001")
    yield from o.home("left")


T7_CLEAR = np.array([0.30, 0.45, 1.10])  # left TCP pose clear of the fully opened drawer (READY is inside it)


def plan_T7(o):
    side = "left"
    # open the top drawer fully (a 14 cm bowl only fits in the part in front of the cabinet top)
    yield from pull_drawer(o, side, "Drawer001", pull=0.225, beta=40, gamma=60, stage_prefix="drawer:")
    p = o.desired[side][0]
    yield from o.move(side, np.r_[p[:2], 1.15], stage="drawer:up")
    # pinch the near (-x) rim, fingers tilted 30 deg forward (offline search: >= 0.3 rad joint margin)
    _, R = tilt_frame(o, side, 30, -15, 0)
    rim = size_of(o, "bowl")[0] / 2 - 0.006
    bowl = o.env.object_center("bowl")
    g = np.array([bowl[0] - rim, bowl[1], bowl[3] - 0.02])
    yield from o.move(side, np.r_[g[:2], 1.15], R, stage="bowl:approach")
    yield from o.move(side, g + 0.06 * UP, R, stage="bowl:approach")
    yield from o.move(side, g, R, speed=0.06, tol=0.005, settle=1.5, stage="bowl:pregrasp")
    yield from o.grip(side, True, 1.2, stage="bowl:grasp")
    yield from o.move(side, np.r_[g[:2], 1.15], R, speed=0.08, stage="bowl:lift")
    # Put the bowl in the exposed front part of the opened drawer, clear of the cabinet's top panel.
    # success_original (obj_inside_of) accepts it: every bowl box corner lies inside a cabinet
    # interior region (its margin is 0.2 m per axis, applied to the fixed closed-drawer regions).
    r = size_of(o, "bowl")[0] / 2
    x = o.env.handle_point("Drawer001")[0] + o.env.drawer_travel("Drawer001") + 0.045 - r - 0.007
    inside = o.env.drawer_inside("Drawer001")
    rest = np.array([x, inside[1], inside[2] + (bowl[3] - bowl[2])])
    yield from place_held(o, side, "bowl", rest, R, clearance=0.13, place_dz=0.015, stage_prefix="bowl:")
    yield from o.move(side, T7_CLEAR, stage="retreat")


def plan_T9(o):
    side = "left"
    bowl = o.env.object_center("bowl")
    inside = o.env.drawer_inside("Drawer003")
    rim = size_of(o, "bowl")[0] / 2 - 0.006
    half = bowl[3] - bowl[2]
    # well inside the open drawer: the hand on the near rim must clear the drawer's front wall, but
    # not reach under the middle drawer's handle
    front = o.env.handle_point("Drawer003")[0] + 0.017
    rest = np.array([front + 0.095, inside[1], inside[2] + half])
    # vertical hand: with the tilted READY hand the palm edge hits the rim (see plan_T1)
    yield from pinch_rim_plan(o, side, "bowl", rest, rim=rim, depth=0.012, clearance=0.12, lift=0.14, place_dz=0.015,
                              R=vertical(o, side, [1.0, 0.0, 0.0]), stage_prefix="bowl:")
    # push the open bottom drawer shut in two stages: (1) READY hand, closed fingertips on the handle
    # bar, until ~6 cm remain; (2) the READY hand would then hit the cabinet face above the drawer,
    # so finish with the fingertips pointing forward (70 deg tilt, 45 deg inward; offline search
    # >= 0.39 rad joint margin) so the palm stays behind the tips
    yield from o.grip(side, True, 0.5, stage="drawer:close_fingers")
    R = ready_R(o, side)
    a = -R[:, 2]
    h = o.env.handle_point("Drawer003")
    bar = h[0] - 0.006  # front of the handle bar
    tip = lambda x: np.array([x, h[1] + 0.03, 0.777]) - 0.031 * a
    yield from o.move(side, tip(bar - 0.04) + 0.08 * UP, R, stage="drawer:approach")
    yield from o.move(side, tip(bar - 0.04), R, speed=0.06, stage="drawer:prepush")
    closed = bar + o.env.drawer_travel("Drawer003")
    yield from o.move(side, tip(closed - 0.06), R, speed=0.06, settle=0.5, stage="drawer:push")
    p = o.desired[side][0]
    yield from o.move(side, p + np.array([-0.04, 0.0, 0.0]), R, speed=0.06, stage="drawer:regrip_pose")
    yield from o.move(side, p + np.array([-0.04, 0.0, 0.05]), R, speed=0.08, stage="drawer:regrip_pose")
    a2, R2 = tilt_frame(o, side, 70, 45, 0)
    h = o.env.handle_point("Drawer003")
    bar = h[0] - 0.006
    tip2 = lambda x: np.array([x, h[1], 0.777]) - 0.031 * a2
    yield from o.move(side, tip2(bar - 0.03) + 0.04 * UP, R2, stage="drawer:regrip_pose")
    yield from o.move(side, tip2(bar - 0.03), R2, speed=0.06, stage="drawer:prepush")
    closed_bar = bar + o.env.drawer_travel("Drawer003")
    yield from o.move(side, tip2(closed_bar + 0.012), R2, speed=0.05, settle=1.5, stage="drawer:push")
    yield from o.move(side, tip2(closed_bar - 0.07) + 0.06 * UP, R2, speed=0.08, stage="drawer:back")
    yield from o.move(side, tip2(closed_bar - 0.07) + 0.16 * UP, R2, speed=0.08, stage="drawer:back")
    # leave the cabinet front before turning the wrist back to READY (turning there drags the drawer)
    yield from o.move(side, np.array([0.38, 0.30, 0.98]), R2, speed=0.10, stage="retreat")
    yield from o.home(side)


def tilt_frame(o, side, tilt_deg, side_deg, roll_deg):
    """Fingers pointing down, tilted `tilt_deg` from vertical toward +x and `side_deg` toward the
    robot centre; closing axis rolled by `roll_deg` about the approach axis."""
    t, g, r = np.radians([tilt_deg, side_deg, roll_deg])
    inward = -1.0 if side == "left" else 1.0
    a = np.array([np.sin(t) * np.cos(g), inward * np.sin(t) * np.sin(g), -np.cos(t)])
    e1 = unit(np.cross(a, [0.0, 1.0, 0.0]))
    e2 = np.cross(a, e1)
    c = np.cos(r) * e1 + np.sin(r) * e2
    return a, nearest_yaw(o, side, [frame(a, c), frame(a, -c)])


def door_angle(o, joint="microjoint"):
    """Current angle (rad) of a fixture door joint."""
    for key in o.env.success.arts:
        for name, v in o.env.fixture_joints(key).items():
            if joint in name:
                return float(v)
    raise KeyError(joint)


def plan_T5(o):
    """Pull the handle ~10 deg, then push the door open from behind its free edge.
    Following the handle all the way winds the right wrist to its joint limits and brings the elbow
    into the torso on the way back; pushing keeps the hand vertical at a fixed yaw."""
    side = "right"
    hinge, handle, theta0 = o.env.microwave_geometry()
    # door plane while closed: the 1 cm slab at the inner (largest x) side of the door link; the
    # handle stands 4.5 cm proud of it, so the hinge->handle line is ~10 deg off the plane
    lo, hi = o.env.link_box("Microwave089_door")
    edge = np.array([hi[0] - 0.005, lo[1]])
    u = edge - hinge[:2]
    r = np.linalg.norm(u) - 0.03  # push 3 cm in from the free edge
    u = u / np.linalg.norm(u)
    n = np.array([-u[1], u[0]])
    n = n if n[0] > 0 else -n  # door normal toward its inner side (+x, away from the robot, when closed)
    z = hi[2] - 0.006  # palm and D405 mount above the door top

    def post(ang, off):
        """Centre of the closed fingers (a 3.2 cm post) at door angle `ang`, `off` from the door
        mid-plane on its inner side: it touches the door at 2.1 cm, clears it at 2.6, pushes at 1.6."""
        return np.r_[hinge[:2] + rot_about(UP, -ang)[:2, :2] @ (r * u + off * n), z]

    # 25 deg pitch: steeper, the far end of the D405 mount (on top) leans into the curved handle bar
    pitch = np.radians(25)
    a = np.array([np.cos(pitch), 0.0, -np.sin(pitch)])
    R = camera_up(side, [frame(a, [0, 1, 0]), frame(a, [0, -1, 0])])
    g = handle - 0.004 * a
    yield from o.move(side, g - 0.10 * a, R, stage="approach")
    yield from o.move(side, g, R, speed=0.05, tol=0.005, settle=1.5, stage="pregrasp")
    yield from o.grip(side, True, 1.0, stage="grasp")
    # pull along the door arc (opening = rotation by -angle about +z); only ~10 deg, further on
    # right_arm_1 (shoulder) reaches its joint limit
    Rz = rot_about(UP, -np.radians(9))
    yield from o.move(side, hinge + Rz @ (g - hinge), Rz @ R, speed=0.06, wspeed=0.5, settle=0.0, stage="open")
    yield from o.wait(0.6)  # hold until the door stops swinging
    # the hand lags the arc goal (the door resists); command where it is so that it does not keep
    # shoving the handle once released
    o.desired[side] = o.tcp(side)
    yield from o.grip(side, False, 0.8, stage="release")
    # the fingertips are inside the handle loop: back straight out along the approach axis as the
    # door has turned it, then lift above the door
    back = rot_about(UP, -door_angle(o)) @ a
    yield from o.move(side, o.desired[side][0] - 0.08 * back + 0.01 * UP, stage="release_back")
    p = o.desired[side][0]
    yield from o.move(side, np.r_[p[:2], z + 0.12], stage="push_lift")
    yield from o.grip(side, True, 0.6, stage="push_close")
    Rv = vertical(o, side, [0.0, 1.0, 0.0])
    yield from o.move(side, o.desired[side][0], Rv, wspeed=0.6, stage="push_turn")
    start = door_angle(o)
    yield from o.move(side, post(start, 0.026) + 0.12 * UP, Rv, stage="push_approach")
    yield from o.move(side, post(start, 0.026), Rv, speed=0.06, tol=0.006, stage="push_insert")
    target = np.radians(80)  # success needs 54 deg (0.6 of the 90 deg range); the door lags the post
    steps = 6
    for k in range(1, steps + 1):
        ang = start + (target - start) * k / steps
        yield from o.move(side, post(ang, 0.016), Rv, speed=0.08, settle=0.0, stage="push")
    yield from o.wait(0.3)
    yield from o.move(side, o.desired[side][0] + 0.10 * UP, Rv, stage="push_up")
    yield from o.home(side)


PLANS = {"T1": plan_T1, "T2": plan_T2, "T3": plan_T3, "T4": plan_T4, "T5": plan_T5,
         "T6": plan_T6, "T7": plan_T7, "T8": plan_T8, "T9": plan_T9, "T10": plan_T10}
