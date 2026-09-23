"""Physics telemetry and terrain-relative collision-surface diagnostics for Rough replay."""
from __future__ import annotations
import math


class RoughMetrics:
    def __init__(self, base):
        import numpy as np
        import torch
        import trimesh
        from pxr import Usd, UsdGeom, UsdPhysics, Gf
        self.t=torch;self.base=base;self.robot=base.scene['robot'];self.sensor=base.scene['contact_forces']
        self.ids,self.names=self.robot.find_joints(base.cfg.joint_names,preserve_order=True)
        if self.names!=base.cfg.joint_names:raise ValueError('Policy joint mapping changed')
        self.wheels=[self.robot.body_names.index(f'{leg}_foot') for leg in ('FR','FL','RR','RL')]
        self.forbidden=[i for i,n in enumerate(self.sensor.body_names) if not n.endswith('_foot')]
        d=self.robot.data
        # Explicit DCMotor limits live in the actuator, not the PhysX 1e9 solver sentinel.
        effort=torch.full_like(d.joint_pos,float('nan'));velocity=torch.full_like(d.joint_pos,float('nan'))
        covered=torch.zeros(d.joint_pos.shape[1],device=base.device,dtype=torch.bool)
        for actuator in self.robot.actuators.values():
            joint_ids=actuator.joint_indices
            if bool(covered[joint_ids].any()):raise ValueError('Overlapping actuator map')
            effort[:,joint_ids]=actuator.effort_limit;velocity[:,joint_ids]=actuator.velocity_limit
            covered[joint_ids]=True
        if not bool(covered.all()):raise ValueError('Unmapped actuator joints')
        self.effort=effort[:,self.ids];self.velocity=velocity[:,self.ids]
        self.position=d.soft_joint_pos_limits[:,self.ids[:12]].clone()
        for label,x in [('effort',self.effort),('velocity',self.velocity),('leg_position',self.position)]:
            if not torch.isfinite(x).all():raise ValueError('Unmapped/nonfinite '+label+' limits: '+str(x[0].tolist()))
        if not (self.effort>0).all() or not (self.velocity>0).all():raise ValueError('Nonpositive actuator limits')
        n=base.num_envs;kw=dict(device=base.device)
        self.energy=torch.zeros((n,16),**kw);self.torque_sat=torch.zeros((n,16),**kw)
        self.velocity_sat=torch.zeros((n,16),**kw);self.torque_clip=torch.zeros((n,16),**kw);self.limit_violations=torch.zeros((n,12),**kw)
        self.ticks=0;self.clearance=[];self.slip=[];self.support_tilt=[];self.normals=[]
        self.support_margin=[];self.support_area=[];self.wheel_gap=[];self.wheel_edge=[]
        self.tilt_time=torch.zeros(n,**kw);self.max_force=torch.zeros(n,**kw)
        # Read collision geometry from the actual spawned USD, in each rigid body's local frame.
        root=base.sim.stage.GetPrimAtPath('/World/envs/env_0/Robot')
        cache=UsdGeom.XformCache();samples=[];body_indices=[];records=[]
        for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
            collision=prim
            while collision and not collision.HasAPI(UsdPhysics.CollisionAPI):collision=collision.GetParent()
            if not collision:continue
            if not prim.IsA(UsdGeom.Boundable):continue
            body=prim
            while body and body.GetName() not in self.robot.body_names:body=body.GetParent()
            if not body or body.GetName().endswith('_foot'):continue
            name=body.GetName();points=None;shape=prim.GetTypeName()
            if prim.IsA(UsdGeom.Mesh):
                points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),dtype=float)
            elif prim.IsA(UsdGeom.Cube):
                half=float(UsdGeom.Cube(prim).GetSizeAttr().Get())/2
                points=np.array([[x,y,z] for x in (-half,half) for y in (-half,half) for z in (-half,half)])
            elif prim.IsA(UsdGeom.Capsule) or prim.IsA(UsdGeom.Cylinder) or prim.IsA(UsdGeom.Sphere):
                obj=UsdGeom.Capsule(prim) if prim.IsA(UsdGeom.Capsule) else UsdGeom.Cylinder(prim) if prim.IsA(UsdGeom.Cylinder) else UsdGeom.Sphere(prim)
                radius=float(obj.GetRadiusAttr().Get());height=float(obj.GetHeightAttr().Get()) if hasattr(obj,'GetHeightAttr') else 0.
                if prim.IsA(UsdGeom.Cylinder):
                    points=np.asarray(trimesh.creation.cylinder(radius=radius,height=height,sections=32).vertices)
                else:
                    sphere=trimesh.creation.icosphere(subdivisions=2,radius=radius)
                    points=np.asarray(sphere.vertices).copy();points[:,2]+=np.sign(points[:,2])*height/2
                axis=str(obj.GetAxisAttr().Get()) if hasattr(obj,'GetAxisAttr') else 'Z'
                if axis=='X':points=points[:,[2,1,0]]
                if axis=='Y':points=points[:,[0,2,1]]
            if points is None:raise ValueError('Unsupported actual collision shape: '+str(prim.GetPath()))
            transform=cache.GetLocalToWorldTransform(prim)*cache.GetLocalToWorldTransform(body).GetInverse()
            points=np.array([transform.Transform(Gf.Vec3d(*p)) for p in points])
            hull=trimesh.convex.convex_hull(points)
            # Hull vertices plus faces' centroids sample lower surfaces, including broad flat faces.
            sampled=np.concatenate((hull.vertices,hull.triangles_center))
            samples.append(sampled);body_indices.extend([self.robot.body_names.index(name)]*len(sampled))
            records.append(dict(body=name,path=str(prim.GetPath()),collision_api_path=str(collision.GetPath()),type=shape,samples=len(sampled)))
        required={n for n in self.robot.body_names if not n.endswith('_foot')}
        if {r['body'] for r in records}!=required:raise ValueError('Not all non-wheel collision bodies mapped')
        self.points=torch.tensor(np.concatenate(samples),device=base.device,dtype=torch.float32)
        self.bodies=torch.tensor(body_indices,device=base.device)
        self.geometry=dict(collisions=records,samples=len(self.points),cadence_hz=50,
                           scope='Actual USD collision hull surface samples vs collision terrain; sampled vertical clearance, not continuous minimum distance. PhysX contacts remain the safety gate.')

    def physics(self,dt):
        t=self.t;d=self.robot.data
        force=self.sensor.data.net_forces_w[:,self.forbidden].norm(dim=-1)
        tensors=(d.root_state_w,d.joint_pos,d.joint_vel,d.applied_torque,force)
        if not all(bool(t.isfinite(v).all()) for v in tensors):raise ValueError('Nonfinite physics telemetry')
        contact=force.amax(1);self.max_force=t.maximum(self.max_force,contact)
        self.tilt_time=t.where(-d.projected_gravity_b[:,2]<.5,self.tilt_time+dt,0.)
        torque=d.applied_torque[:,self.ids];vel=d.joint_vel[:,self.ids]
        self.energy+=(torque*vel).abs()*dt
        self.torque_sat+=(torque.abs()>=.99*self.effort)
        self.torque_clip+=(d.computed_torque[:,self.ids]-torque).abs()>1e-4
        self.velocity_sat+=(vel.abs()>=.99*self.velocity)
        pos=d.joint_pos[:,self.ids[:12]]
        self.limit_violations+=(pos<self.position[:,:12,0])|(pos>self.position[:,:12,1])
        self.ticks+=1
        return contact,self.tilt_time>.1+1e-7

    def sample_geometry(self):
        t=self.t;d=self.robot.data
        from isaaclab.utils.math import quat_apply
        from isaaclab.utils.warp import raycast_mesh
        n=self.base.num_envs
        q=d.body_link_quat_w[:,self.bodies];p=d.body_link_pos_w[:,self.bodies]
        world=p+quat_apply(q.reshape(-1,4),self.points.expand(n,-1,-1).reshape(-1,3)).reshape(n,-1,3)
        starts=world.clone();starts[...,2]+=5
        directions=t.zeros_like(starts);directions[...,2]=-1
        mesh=self.base.scene['height_scanner'].meshes['/World/ground']
        hits,_,_,_=raycast_mesh(starts,directions,mesh)
        if not t.isfinite(hits).all():raise ValueError('Collision clearance ray missed terrain')
        self.clearance.append((world[...,2]-hits[...,2]).amin(1))
        centers=d.body_link_pos_w[:,self.wheels];starts=centers.clone();starts[...,2]+=5
        direction=t.zeros_like(starts);direction[...,2]=-1
        hit,_,normal,_=raycast_mesh(starts,direction,mesh,return_normal=True)
        if not t.isfinite(hit).all() or not t.isfinite(normal).all():raise ValueError('Wheel support rays missed')
        velocity=d.body_link_lin_vel_w[:,self.wheels]+t.cross(d.body_link_ang_vel_w[:,self.wheels],hit-centers,dim=-1)
        tangent=velocity-(velocity*normal).sum(-1,keepdim=True)*normal
        self.slip.append(tangent.norm(dim=-1))
        mean=normal.mean(1);mean=mean/mean.norm(dim=-1,keepdim=True).clamp_min(1e-8)
        z=t.zeros((n,3),device=self.base.device);z[:,2]=1
        up=quat_apply(d.root_quat_w,z)
        self.support_tilt.append(t.acos((up*mean).sum(1).clamp(-1,1))*180/math.pi)
        self.normals.append(mean)
        polygon=hit[:,[0,1,3,2],:2];end=polygon.roll(-1,dims=1);edge=end-polygon
        twice_area=(polygon[:,:,0]*end[:,:,1]-polygon[:,:,1]*end[:,:,0]).sum(1)
        offset=d.root_pos_w[:,None,:2]-polygon
        signed=(edge[:,:,0]*offset[:,:,1]-edge[:,:,1]*offset[:,:,0])*twice_area.sign()[:,None]
        self.support_margin.append((signed/edge.norm(dim=-1).clamp_min(1e-8)).amin(1))
        self.support_area.append(twice_area.abs()/2)
        self.wheel_gap.append(centers[:,:,2]-hit[:,:,2])
        local=centers[:,:,:2]-self.base.scene.env_origins[:,None,:2]
        self.wheel_edge.append((6.-local.abs()).amin((1,2)))

    def finish(self):
        t=self.t
        clearance=t.stack(self.clearance);slip=t.stack(self.slip);tilt=t.stack(self.support_tilt)
        return dict(geometry=self.geometry,clearance_min_m=clearance.amin(0).tolist(),
                    clearance_p01_m=t.quantile(clearance,.01,dim=0).tolist(),
                    wheel_slip_p95_m_s=t.quantile(slip,.95,dim=0).tolist(),
                    wheel_slip_max_m_s=slip.amax(0).tolist(),support_tilt_max_deg=tilt.amax(0).tolist(),
                    support_normal_mean=t.stack(self.normals).mean(0).tolist(),
                    absolute_mechanical_energy_j=self.energy.tolist(),torque_saturation_fraction=(self.torque_sat/self.ticks).tolist(),
                    torque_clipping_fraction=(self.torque_clip/self.ticks).tolist(),velocity_saturation_fraction=(self.velocity_sat/self.ticks).tolist(),joint_limit_violation_steps=self.limit_violations.tolist(),
                    projected_four_wheel_polygon_min_area_m2=t.stack(self.support_area).amin(0).tolist(),
                    base_projection_min_support_margin_m=t.stack(self.support_margin).amin(0).tolist(),
                    wheel_center_surface_gap_min_m=t.stack(self.wheel_gap).amin(0).tolist(),
                    minimum_wheel_center_distance_to_tile_edge_m=t.stack(self.wheel_edge).amin(0).tolist(),
                    effort_limits=self.effort[0].tolist(),velocity_limits=self.velocity[0].tolist(),continuous_position_joints=self.names[12:],physics_samples=self.ticks,
                    caveat='Wheel implicit-actuator torque is a simulator estimate; slip uses terrain projection even without contact. No hardware torque-speed qualification.')
