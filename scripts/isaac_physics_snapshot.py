"""Serialize resolved live PhysX parameters; no simulator imports at module load."""
from __future__ import annotations


def plain(value):
    if value is None or isinstance(value,(str,bool,int,float)):return value
    if isinstance(value,dict):return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    if hasattr(value,"detach"):return value.detach().cpu().tolist()
    if hasattr(value,"tolist"):return value.tolist()
    if isinstance(value,type):return value.__module__+"."+value.__qualname__
    return str(value)


def resolved_snapshot(robot, joint_ids, cfg):
    view=robot.root_physx_view
    body={key:plain(getattr(view,method)()[0]) for key,method in (
        ("mass_kg","get_masses"),("inertia_raw","get_inertias"),("com_pose_raw","get_coms"))}
    body["material_properties_raw"]=plain(view.get_material_properties()[0])
    joint={key:plain(getattr(view,method)()[0,joint_ids]) for key,method in (
        ("stiffness","get_dof_stiffnesses"),("damping","get_dof_dampings"),
        ("armature","get_dof_armatures"),("max_velocity_rad_s","get_dof_max_velocities"),
        ("max_force_nm","get_dof_max_forces"),("limits_rad","get_dof_limits"))}
    if hasattr(view,"get_dof_friction_properties"):
        joint["friction_properties_raw"]=plain(view.get_dof_friction_properties()[0,joint_ids])
    else:
        joint["friction_coefficient"]=plain(view.get_dof_friction_coefficients()[0,joint_ids])
    models={}
    for name,actuator in robot.actuators.items():
        models[name]={"class":type(actuator).__module__+"."+type(actuator).__qualname__,
            "cfg":plain(actuator.cfg.to_dict()),
            "resolved":{key:plain(getattr(actuator,key)) for key in
                ("joint_names","joint_indices","stiffness","damping","armature","friction",
                 "effort_limit","velocity_limit") if hasattr(actuator,key)}}
    return {"live_physx":True,"body_names":robot.body_names,"body":body,
        "total_mass_kg":sum(body["mass_kg"]),"joint_names":[robot.joint_names[i] for i in joint_ids],
        "joint_physx":joint,"actuator_models":models,
        "physics_dt_s":cfg.sim.dt,"policy_dt_s":cfg.sim.dt*cfg.decimation,
        "asset_spawn_cfg":plain(cfg.scene.robot.spawn.to_dict()),
        "notes":["COM/inertia retain PhysX tensor API frames and layout; do not compare raw orientations across engines",
                 "Explicit legs have separate actuator gains and PhysX drive gains",
                 "Isaac implicit wheel applied_torque is a PD estimate, not a measured current or solver torque"]}


def target_guard_events(targets, positions, velocities, step, entries, ranges, wheel_limit=50.):
    """Counterfactual DDS guard only; never change PhysX targets or history."""
    events=[]
    for index,(policy,case,seed) in enumerate(entries):
        violations=[]
        for slot,target in enumerate(targets[index]):
            lower,upper=ranges[slot] if slot<12 else (-wheel_limit,wheel_limit)
            if target<lower or target>upper:
                violations.append({"slot":slot,"target":float(target),"limits":[float(lower),float(upper)],
                    "measured_q":float(positions[index,slot]),"measured_dq":float(velocities[index,slot])})
        if violations:events.append({"entry":index,"policy":policy,"case":case.name,"seed":seed,
            "policy_tick":step,"time_s":step*.02,"violations":violations})
    return events
