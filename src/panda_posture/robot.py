"""Panda model discovery, geometry queries and physical velocity actuation."""
from itertools import combinations
import numpy as np
import pybullet as p
import pybullet_data


class Panda:
    def __init__(self, cfg, gui=False):
        self.cfg = cfg
        self.client = p.connect(p.GUI if gui else p.DIRECT)
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=self.client)
        p.setTimeStep(cfg['dt'], physicsClientId=self.client)
        p.setGravity(*cfg['gravity'], physicsClientId=self.client)
        p.setPhysicsEngineParameter(numSolverIterations=cfg['solver_iterations'],
            deterministicOverlappingPairs=1, physicsClientId=self.client)
        self.body = p.loadURDF('franka_panda/panda.urdf', useFixedBase=True,
            flags=p.URDF_USE_SELF_COLLISION, physicsClientId=self.client)
        self.joints = [p.getJointInfo(self.body, i, physicsClientId=self.client)
                       for i in range(p.getNumJoints(self.body, physicsClientId=self.client))]
        by_name = {j[1].decode(): j[0] for j in self.joints}
        self.link_names = {-1: p.getBodyInfo(self.body, physicsClientId=self.client)[0].decode()}
        self.link_names.update({j[0]: j[12].decode() for j in self.joints})
        self.arm_indices = [by_name[f'panda_joint{i}'] for i in range(1, 8)]
        self.finger_indices = [by_name[f'panda_finger_joint{i}'] for i in (1, 2)]
        self.tool_link = next(i for i, name in self.link_names.items() if name == 'panda_grasptarget')
        self.movable = sorted([j[0] for j in self.joints if j[3] >= 0], key=lambda i: self.joints[i][3])
        self.arm_columns = [self.movable.index(i) for i in self.arm_indices]
        assert len(self.movable) == 9, 'Unexpected model DOF; revalidate Jacobian mapping'
        assert all(self.joints[i][2] == p.JOINT_REVOLUTE for i in self.arm_indices)
        self.lower = np.array([self.joints[i][8] for i in self.arm_indices])
        self.upper = np.array([self.joints[i][9] for i in self.arm_indices])
        self.efforts = np.array([self.joints[i][10] for i in self.arm_indices])
        self.speed_limits = np.minimum(cfg['arm_speed_limit'], [self.joints[i][11] for i in self.arm_indices])
        self.collision_links = [i for i in self.link_names
            if p.getCollisionShapeData(self.body, i, physicsClientId=self.client)]
        self.excluded_pairs = []
        self.self_pairs = []
        # Only physically connected direct neighbors and one rigid assembly pair.
        # Do not broadly exclude grandparent pairs: link5/link7 can collide.
        for a, b in combinations(self.collision_links, 2):
            reason = None
            if (b >= 0 and self.joints[b][16] == a) or (a >= 0 and self.joints[a][16] == b):
                reason = 'direct parent-child collision meshes overlap at the joint'
            if {self.link_names[a], self.link_names[b]} == {'panda_link7', 'panda_hand'}:
                reason = 'rigid connection through collision-free panda_link8'
            if reason:
                self.excluded_pairs.append({'a': a, 'b': b, 'names': [self.link_names[a], self.link_names[b]], 'reason': reason})
                p.setCollisionFilterPair(self.body, self.body, a, b, 0, physicsClientId=self.client)
            else:
                self.self_pairs.append((a,b))
                p.setCollisionFilterPair(self.body, self.body, a, b, 1, physicsClientId=self.client)
        self.obstacle = None
        self.reset(cfg['q_initial'])

    def reset(self, q):
        """Initialization / numerical diagnostics ONLY. Never called by step()."""
        for i, qi in zip(self.arm_indices, q):
            p.resetJointState(self.body, i, float(qi), 0.0, physicsClientId=self.client)
        for i in self.finger_indices:
            p.resetJointState(self.body, i, self.cfg['finger_position'], 0.0, physicsClientId=self.client)
        self.hold_fingers()
        p.performCollisionDetection(physicsClientId=self.client)

    def hold_fingers(self):
        p.setJointMotorControlArray(self.body, self.finger_indices, p.POSITION_CONTROL,
            targetPositions=[self.cfg['finger_position']]*2, targetVelocities=[0]*2,
            forces=[self.joints[i][10] for i in self.finger_indices],
            positionGains=[1.0]*2, velocityGains=[1.0]*2, physicsClientId=self.client)

    def state(self):
        states = p.getJointStates(self.body, self.arm_indices, physicsClientId=self.client)
        return np.array([s[0] for s in states]), np.array([s[1] for s in states]), np.array([s[3] for s in states])

    def finger_state(self):
        return np.array([s[0] for s in p.getJointStates(self.body, self.finger_indices, physicsClientId=self.client)])

    def position(self):
        # getLinkState[4] is the world URDF-link frame (not COM [0]).
        return np.asarray(p.getLinkState(self.body, self.tool_link,
            computeForwardKinematics=True, physicsClientId=self.client)[4])

    def jacobian(self, link=None, local_point=None):
        link = self.tool_link if link is None else link
        point = [0,0,0] if local_point is None else local_point
        q = [s[0] for s in p.getJointStates(self.body, self.movable, physicsClientId=self.client)]
        j, _ = p.calculateJacobian(self.body, link, point, q, [0.0]*len(q), [0.0]*len(q), physicsClientId=self.client)
        full = np.asarray(j)
        assert full.shape == (3, len(self.movable))
        return full[:, self.arm_columns]

    def command_velocity(self, velocity):
        velocity = np.asarray(velocity)
        if velocity.shape != (7,) or not np.all(np.isfinite(velocity)):
            raise ValueError('Velocity must be finite with shape (7,)')
        if np.any(np.abs(velocity) > self.speed_limits + 1e-12):
            raise ValueError('Velocity outside shared interface limits')
        p.setJointMotorControlArray(self.body, self.arm_indices, p.VELOCITY_CONTROL,
            targetVelocities=velocity.tolist(), forces=self.efforts.tolist(),
            velocityGains=[1.0]*7, physicsClientId=self.client)
        self.hold_fingers()
        p.stepSimulation(physicsClientId=self.client)

    def joint_limit_violation(self, q):
        q = np.asarray(q)
        if q.shape != (7,):
            raise ValueError('Joint position must have shape (7,)')
        if not np.all(np.isfinite(q)):
            return True
        eps = self.cfg['joint_limit_tolerance']
        return bool(np.any(q < self.lower-eps) or np.any(q > self.upper+eps))

    def add_sphere(self, center, radius):
        if self.obstacle is not None:
            p.removeBody(self.obstacle, physicsClientId=self.client)
        collision = p.createCollisionShape(p.GEOM_SPHERE, radius=radius, physicsClientId=self.client)
        visual = p.createVisualShape(p.GEOM_SPHERE, radius=radius, rgbaColor=[0.9,0.2,0.1,0.8], physicsClientId=self.client)
        self.obstacle = p.createMultiBody(baseMass=0, baseCollisionShapeIndex=collision,
            baseVisualShapeIndex=visual, basePosition=center, physicsClientId=self.client)
        p.performCollisionDetection(physicsClientId=self.client)
        return self.obstacle

    def collision_report(self, query_distance=2.0):
        """Geometric signed separation in meters. Includes base, arm, hand, fingers.

        Uses explicit pairs independent of broadphase contact-cache timing.
        query_distance caps *reported* clearance if no point lies in range.
        """
        self_min = query_distance
        obstacle_min = query_distance if self.obstacle is not None else None
        collisions = []
        threshold = self.cfg['collision_distance_threshold']
        for a,b in self.self_pairs:
            pts = p.getClosestPoints(self.body,self.body,query_distance,
                linkIndexA=a, linkIndexB=b, physicsClientId=self.client)
            for pt in pts:
                self_min = min(self_min, pt[8])
                if pt[8] <= threshold:
                    collisions.append({'type':'self', 'a':a, 'b':b, 'distance':pt[8]})
        if self.obstacle is not None:
            for pt in p.getClosestPoints(self.body,self.obstacle,query_distance,physicsClientId=self.client):
                obstacle_min = min(obstacle_min,pt[8])
                if pt[8] <= threshold:
                    collisions.append({'type':'obstacle','a':pt[3],'b':pt[4],'distance':pt[8]})
        return {'collision': bool(collisions), 'pairs':collisions,
                'self_clearance':float(self_min), 'obstacle_clearance':obstacle_min}

    def model_info(self):
        return {'arm_indices':self.arm_indices, 'finger_indices':self.finger_indices,
            'tool_link':self.tool_link, 'tool_name':self.link_names[self.tool_link],
            'tool_point_link_frame':[0,0,0], 'movable_indices':self.movable,
            'arm_jacobian_columns':self.arm_columns, 'full_jacobian_shape':[3,len(self.movable)],
            'lower_rad':self.lower.tolist(), 'upper_rad':self.upper.tolist(),
            'motor_effort_Nm':self.efforts.tolist(), 'velocity_limit_rad_s':self.speed_limits.tolist(),
            'collision_links':self.collision_links, 'link_names':self.link_names,
            'self_pairs':self.self_pairs, 'excluded_pairs':self.excluded_pairs,
            'joint_inventory':[{'index':j[0], 'joint':j[1].decode(), 'link':j[12].decode(),
                'type':j[2], 'q_index':j[3], 'u_index':j[4], 'parent':j[16]} for j in self.joints]}

    def close(self):
        if p.isConnected(self.client):
            p.disconnect(self.client)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
