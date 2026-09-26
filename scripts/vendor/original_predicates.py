# Copyright 2025 Lightwheel Team; extracted from LW-BenchHub under Apache-2.0.
# Source commit b2bcb2d00edef691f9fcc49039cbf0bcc7464605. See source_manifest.json and LICENSE.
# Generated predicate bodies: do not change semantics here.
from __future__ import annotations
import sys
import numpy as np
import torch
from scipy.spatial.transform import Rotation
from types import SimpleNamespace
T = SimpleNamespace(convert_quat=lambda q,to: np.roll(q,-1) if to=='xyzw' else np.roll(q,1))
OU = sys.modules[__name__]
def matrix_from_quat(q):
    # IsaacLab convention wxyz; SciPy conversion is algebraically equivalent.
    return torch.as_tensor(Rotation.from_quat(q.detach().cpu().numpy()[..., [1,2,3,0]]).as_matrix(),dtype=q.dtype,device=q.device)


def obj_inside_of(env: ManagerBasedEnv, obj_name: str, fixture_id: str, partial_check: bool=False, th=0.2) -> torch.Tensor:
    """
    whether an object (another mujoco object) is inside of fixture. applies for most fixtures
    """
    obj = env.cfg.isaaclab_arena_env.task.objects[obj_name]
    fixture = env.cfg.isaaclab_arena_env.task.get_fixture(fixture_id)
    fixtr_int_regions = fixture.get_int_sites(relative=False)
    check = []
    for i in range(env.cfg.scene.num_envs):
        inside_of = False
        for reset_region in fixtr_int_regions.values():
            inside_of = True
            fixtr_p0, fixtr_px, fixtr_py, fixtr_pz = [r + env.scene.env_origins[i].cpu().numpy() for r in reset_region]
            u = fixtr_px[i] - fixtr_p0[i]
            v = fixtr_py[i] - fixtr_p0[i]
            w = fixtr_pz[i] - fixtr_p0[i]
            if obj_name in env.scene.articulations:
                obj_pos = env.scene.articulations[obj_name].data.body_com_pos_w[i, 0, :].cpu().numpy()
                obj_quat = T.convert_quat(env.scene.articulations[obj_name].data.body_com_quat_w[i, 0, :].cpu().numpy(), to='xyzw')
            elif obj_name in env.scene.rigid_objects:
                obj_pos = env.scene.rigid_objects[obj_name].data.body_com_pos_w[i, 0, :].cpu().numpy()
                obj_quat = T.convert_quat(env.scene.rigid_objects[obj_name].data.body_com_quat_w[i, 0, :].cpu().numpy(), to='xyzw')
            if partial_check:
                obj_points_to_check = [obj_pos]
                th_u = th_v = th_w = 0.0
            else:
                obj_points_to_check = obj.get_bbox_points(trans=obj_pos, rot=obj_quat)
                base_alpha = th
                min_th = 0.0001
                lu = np.linalg.norm(u) if np.linalg.norm(u) > 0 else 0.0
                lv = np.linalg.norm(v) if np.linalg.norm(v) > 0 else 0.0
                lw = np.linalg.norm(w) if np.linalg.norm(w) > 0 else 0.0
                th_u = max(min_th, lu * base_alpha)
                th_v = max(min_th, lv * base_alpha)
                th_w = max(min_th, lw * base_alpha)
            for obj_p in obj_points_to_check:
                check1 = np.dot(u, fixtr_p0[i]) - th_u <= np.dot(u, obj_p) <= np.dot(u, fixtr_px[i]) + th_u
                check2 = np.dot(v, fixtr_p0[i]) - th_v <= np.dot(v, obj_p) <= np.dot(v, fixtr_py[i]) + th_v
                check3 = np.dot(w, fixtr_p0[i]) - th_w <= np.dot(w, obj_p) <= np.dot(w, fixtr_pz[i]) + th_w
                if not (check1 and check2 and check3):
                    inside_of = False
                    break
            if inside_of:
                check.append(True)
                break
        if not inside_of:
            check.append(False)
    return torch.tensor(check, dtype=torch.bool, device=env.device)

def check_obj_in_receptacle_no_contact(env: ManagerBasedEnv, obj_name: str, receptacle_name: str, th: float=None) -> torch.Tensor:
    """
    check if object is in receptacle object based on threshold
    """
    if obj_name in env.scene.articulations:
        obj_pos = env.scene.articulations[obj_name].data.body_com_pos_w[:, 0, :]
    elif obj_name in env.scene.rigid_objects:
        obj_pos = env.scene.rigid_objects[obj_name].data.body_com_pos_w[:, 0, :]
    if receptacle_name in env.scene.articulations:
        recep_pos = env.scene.articulations[receptacle_name].data.body_com_pos_w[:, 0, :]
    elif receptacle_name in env.scene.rigid_objects:
        recep_pos = env.scene.rigid_objects[receptacle_name].data.body_com_pos_w[:, 0, :]
    if th is None:
        th = env.cfg.isaaclab_arena_env.task.objects[receptacle_name].horizontal_radius * 0.7
    is_closed = torch.norm(obj_pos[:, :2] - recep_pos[:, :2], dim=-1) < th
    return is_closed

def gripper_obj_far(env, obj_name='obj', th=0.25, eef_name=None, force_th=0.1) -> torch.Tensor:
    """
    check if gripper is far from object based on distance defined by threshold
    """
    if obj_name in env.cfg.isaaclab_arena_env.task.objects and obj_name in env.scene.rigid_objects:
        obj_pos = env.scene.rigid_objects[obj_name].data.body_com_pos_w
    else:
        if not isinstance(obj_name, str):
            obj_name = obj_name.name
        articulation_obj = env.scene.articulations[obj_name]
        obj_pos = articulation_obj.data.body_com_pos_w
    if eef_name is None:
        gripper_site_pos = env.scene['ee_frame'].data.target_pos_w
    else:
        eef_frame_data = env.scene['ee_frame'].data
        eef_index = eef_frame_data.target_frame_names.index(eef_name)
        gripper_site_pos = eef_frame_data.target_pos_w[:, eef_index:eef_index + 1, :]
    gripper_expanded = gripper_site_pos.unsqueeze(2)
    obj_expanded = obj_pos.unsqueeze(1)
    distances = torch.norm(gripper_expanded - obj_expanded, dim=-1)
    distance_check = torch.all(distances > th, dim=-1)
    distance_far = torch.all(distance_check, dim=-1)
    force_check = torch.ones(env.num_envs, dtype=torch.bool, device=env.device)
    if 'left_gripper_contact' in env.scene.sensors:
        left_force = env.scene.sensors['left_gripper_contact']._data.net_forces_w[:, 0, :]
        left_force_norm = torch.norm(left_force, dim=-1)
        force_check &= left_force_norm < force_th
    if 'right_gripper_contact' in env.scene.sensors:
        right_force = env.scene.sensors['right_gripper_contact']._data.net_forces_w[:, 0, :]
        right_force_norm = torch.norm(right_force, dim=-1)
        force_check &= right_force_norm < force_th
    return distance_far & force_check

def check_place_obj1_on_obj2(env: ManagerBasedEnv, obj1: str, obj2: str, th_z_axis_cos: float=0.8, th_xy_dist: float=0.25, th_xyz_vel: float=0.5, gipper_th: float=0.25) -> dict:
    """
    check if obj1 is placed on obj2
    obj1 and obj2 must be a fixture moveable or a object

    Args:
        env (Env): environment
        obj1 : name of object 1 or a moveable fixture
        obj2 : name of object 2 or a moveable fixture
        th_z_axis_cos (float): threshold for z-axis cosine similarity
        th_xy_dist (float): threshold for xy distance
        th_xyz_vel (float): threshold for xyz velocity
        gipper_th (float): threshold for gripper distance

    Returns:
        dict: success state of the task with tensor values for multi-env support
        - gripper_far: check if gripper is far from obj1 and obj2 (tensor)
        - obj1_is_standing: check if obj1 is standing (tensor)
        - obj1_in_obj2: check if obj1 is in obj2 (tensor)
        - obj1_stable: check if obj1 is stable (tensor)
        - obj1_contact_with_obj2: check if obj1 is in contact with obj2 (tensor)

    """
    import torch
    if obj1 in env.cfg.isaaclab_arena_env.task.objects:
        if obj1 in env.scene.rigid_objects:
            obj1_obj = env.cfg.isaaclab_arena_env.task.objects[obj1]
            obj1_pos = torch.mean(env.scene.rigid_objects[obj1].data.body_com_pos_w, dim=1)
            obj1_vel = torch.mean(env.scene.rigid_objects[obj1].data.body_com_vel_w, dim=1)
            obj1_quat = torch.mean(env.scene.rigid_objects[obj1].data.body_com_quat_w, dim=1)
            obj1_rot_mat = matrix_from_quat(obj1_quat)
        elif obj1 in env.scene.articulations:
            obj1_obj = env.cfg.isaaclab_arena_env.task.objects[obj1]
            obj1_pos = torch.mean(env.scene.articulations[obj1].data.body_com_pos_w, dim=1)
            obj1_vel = torch.mean(env.scene.articulations[obj1].data.body_com_vel_w, dim=1)
            obj1_quat = torch.mean(env.scene.articulations[obj1].data.body_com_quat_w, dim=1)
            obj1_rot_mat = matrix_from_quat(obj1_quat)
    else:
        obj1_name = obj1 if isinstance(obj1, str) else obj1.name
        obj1_pos = env.scene.state['articulation'][obj1_name]['root_pose'][:, :3]
        obj1_quat = env.scene.state['articulation'][obj1_name]['root_pose'][:, 3:]
        obj1_rot_mat = matrix_from_quat(obj1_quat)
        obj1_vel = env.scene.state['articulation'][obj1_name]['root_velocity'][:, :3]
    if obj2 in env.cfg.isaaclab_arena_env.task.objects:
        if obj2 in env.scene.rigid_objects:
            obj2_obj = env.cfg.isaaclab_arena_env.task.objects[obj2]
            obj2_pos = torch.mean(env.scene.rigid_objects[obj2].data.body_com_pos_w, dim=1)
        elif obj2 in env.scene.articulations:
            obj2_obj = env.cfg.isaaclab_arena_env.task.objects[obj2]
            obj2_pos = torch.mean(env.scene.articulations[obj2].data.body_com_pos_w, dim=1)
    else:
        obj2_obj = obj2
        obj2_name = obj2 if isinstance(obj2, str) else obj2.name
        obj2_pos = env.scene.state['articulation'][obj2_name]['root_pose'][:, :3]
    obj1_z_axis = obj1_rot_mat[:, :, 2]
    world_z_axis = torch.tensor([0.0, 0.0, 1.0], device=env.device, dtype=obj1_z_axis.dtype)
    z_axis_cos = torch.abs(torch.sum(obj1_z_axis * world_z_axis, dim=-1))
    xy_dist = torch.norm(obj1_pos[:, :2] - obj2_pos[:, :2], dim=-1)
    obj1_obj2_size_xy_min = min(obj2_obj.size[:2])
    xyz_vel = torch.norm(obj1_vel, dim=-1)
    gripper_far_obj1 = gripper_obj_far(env, obj1, th=gipper_th)
    gripper_far_obj2 = gripper_obj_far(env, obj2, th=gipper_th)
    gripper_far = gripper_far_obj1 & gripper_far_obj2
    obj1_is_standing = z_axis_cos > th_z_axis_cos
    obj1_in_obj2 = xy_dist < obj1_obj2_size_xy_min * th_xy_dist
    obj1_stable = xyz_vel < th_xyz_vel
    return gripper_far & obj1_is_standing & obj1_in_obj2 & obj1_stable

def normalize_joint_value(raw: float, joint_min: float, joint_max: float) -> float:
    """
    normalize raw value to be between 0 and 1
    """
    return (raw - joint_min) / (joint_max - joint_min)

def get_joint_state(self, env, joint_names, env_ids=None):
    """
        Args:
            env (ManagerBasedRLEnv): environment

        Returns:
            dict: maps door names to a percentage of how open they are
        """
    joint_state = dict()
    for j_name in joint_names:
        joint_idx = env.scene.articulations[self.name].data.joint_names.index(j_name)
        joint_qpos = env.scene.articulations[self.name].data.joint_pos[:, joint_idx]
        joint_range = env.scene.articulations[self.name].data.joint_pos_limits[0, joint_idx, :]
        joint_min, joint_max = (joint_range[0], joint_range[1])
        norm_qpos = OU.normalize_joint_value(joint_qpos, joint_min=joint_min, joint_max=joint_max)
        if joint_min < 0:
            norm_qpos = 1 - norm_qpos
        joint_state[j_name] = norm_qpos
    return joint_state

def is_open(self, env, joint_names=None, th=0.9):
    if joint_names is None:
        joint_names = self.door_joint_names
    joint_state = self.get_joint_state(env, joint_names)
    is_open = torch.tensor([True], device=env.device).repeat(env.num_envs)
    for j_name in joint_names:
        assert j_name in joint_state
        norm_qpos = joint_state[j_name]
        is_open = is_open & (norm_qpos >= th)
    return is_open

def is_closed(self, env, joint_names=None, th=0.005):
    if joint_names is None:
        joint_names = self.door_joint_names
    joint_state = self.get_joint_state(env, joint_names)
    is_closed = torch.tensor([True], device=env.device).repeat(env.num_envs)
    for j_name in joint_names:
        assert j_name in joint_state
        norm_qpos = joint_state[j_name]
        is_closed = is_closed & (norm_qpos <= th)
    return is_closed

def check_success_caller(self, env):
    arena_env = env.cfg.isaaclab_arena_env
    arena_env.orchestrator.update_state(env)
    for checker in arena_env.task.checkers:
        arena_env.task.checker_results[checker.type] = checker.check(env)
    success_check_result = self._check_success(env)
    assert isinstance(success_check_result, torch.Tensor), f'_check_success must be a torch.Tensor, but got {type(success_check_result)}'
    assert len(success_check_result.shape) == 1 and success_check_result.shape[0] == env.num_envs, f'_check_success must be a torch.Tensor of shape ({env.num_envs},), but got {success_check_result.shape}'
    start_check_count = torch.tensor(self._start_success_check_count, device=env.episode_length_buf.device, dtype=env.episode_length_buf.dtype)
    success_check_result &= env.episode_length_buf >= start_check_count
    self._success_flag &= self._success_cache < self._success_count
    self._success_cache *= self._success_cache < self._success_count
    self._success_flag |= success_check_result
    self._success_cache += self._success_flag.int()
    return self._success_cache >= self._success_count

def check_T1(self, env):
    th = env.cfg.isaaclab_arena_env.task.objects['plate'].horizontal_radius
    bowl_in_plate = OU.check_obj_in_receptacle_no_contact(env, 'akita_black_bowl', 'plate', th)
    return bowl_in_plate & OU.gripper_obj_far(env, 'akita_black_bowl')

def check_T2(self, env):
    """
        Check if the bowl is placed on the plate.
        """
    is_gripper_obj_far = OU.gripper_obj_far(env, self.bowl_target)
    bowl_pos = torch.mean(env.scene.rigid_objects[self.bowl_target].data.body_com_pos_w, dim=1)
    plate_pos = torch.mean(env.scene.rigid_objects[self.plate].data.body_com_pos_w, dim=1)
    xy_distance = torch.norm(bowl_pos[:, :2] - plate_pos[:, :2], dim=1)
    bowl_centered = xy_distance < 0.08
    z_diff = bowl_pos[:, 2] - plate_pos[:, 2]
    bowl_on_plate_height = (z_diff > 0.01) & (z_diff < 0.15)
    bowl_vel = torch.mean(env.scene.rigid_objects[self.bowl_target].data.body_com_vel_w, dim=1)
    bowl_speed = torch.norm(bowl_vel, dim=1)
    bowl_stable = bowl_speed < 0.05
    success = is_gripper_obj_far & bowl_centered & bowl_on_plate_height & bowl_stable
    return success

def check_T3(self, env):
    return OU.check_place_obj1_on_obj2(env, self.ketchup, self.basket, th_z_axis_cos=0, th_xy_dist=0.4, th_xyz_vel=0.5)

def check_T4(self, env):
    return self.drawer.is_open(env, [self.top_joint_name], th=0.5) & OU.gripper_obj_far(env, self.drawer.name, th=0.4)

def check_T5(self, env):
    return self.microwave.is_open(env, th=0.6) & OU.gripper_obj_far(env, self.microwave.name)

def check_T6(self, env):
    knobs_state = self.stove.get_knobs_state(env)
    knob_success = torch.tensor([False], device=env.device).repeat(env.num_envs)
    for knob_name, knob_value in knobs_state.items():
        abs_knob = torch.abs(knob_value)
        lower, upper = (0.35, 2 * np.pi - 0.35)
        knob_on = (abs_knob >= lower) & (abs_knob <= upper)
        knob_success = knob_success | knob_on
    gripper_far_from_stove = OU.gripper_obj_far(env, self.stove.name, th=0.3)
    return knob_success & gripper_far_from_stove

def check_T7(self, env):
    drawer_open = self.drawer.is_open(env, [self.top_drawer_joint_name], th=0.3)
    bowl_in_drawer = OU.obj_inside_of(env, self.akita_black_bowl, 'storage_furniture')
    gripper_far = OU.gripper_obj_far(env, self.akita_black_bowl)
    return drawer_open & bowl_in_drawer & gripper_far

def check_T8(self, env):
    return OU.check_place_obj1_on_obj2(env, self.akita_black_bowl_middle, self.akita_black_bowl_back, th_z_axis_cos=0.5, th_xy_dist=1.0, th_xyz_vel=0.5, gipper_th=0.3)

def check_T9(self, env):
    bowl_success = OU.obj_inside_of(env, 'akita_black_bowl', self.drawer)
    return bowl_success & OU.gripper_obj_far(env, 'akita_black_bowl') & self.drawer.is_closed(env, [self.bottom_drawer_joint_name])

def check_T10(self, env):
    success_alphabet_soup = OU.check_place_obj1_on_obj2(env, self.alphabet_soup, self.basket, th_z_axis_cos=0, th_xy_dist=0.4, th_xyz_vel=0.5)
    success_tomato_sauce = OU.check_place_obj1_on_obj2(env, self.tomato_sauce, self.basket, th_z_axis_cos=0, th_xy_dist=0.4, th_xyz_vel=0.5)
    return success_alphabet_soup & success_tomato_sauce
