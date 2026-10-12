"""One-reset complete Flat v2 command prefix for resolved live PhysX audit."""
from dataclasses import asdict
import locomotion_v2_protocol as reference
from run_support import ROOT

POLICIES=(24650,)
EXPORT_DIRS={24650:ROOT/"policies/local/core_24650/export"}
SEED_START=73001
SEEDS=1
TERRAINS=("flat_mu_100",)
cases_for=reference.cases_for
geometry=reference.geometry
meshes_for=reference.meshes_for
stair_exposure=reference.stair_exposure
coverage=reference.coverage
assess=reference.assess
finalize_result=reference.finalize_result


def protocol_manifest(export_dirs=None):
    result=reference.protocol_manifest(EXPORT_DIRS if export_dirs is None else export_dirs)
    result.update(schema="b2w_sim2sim_isaac_audit_v1",stage="one_reset_diagnostic",
        variants={name:{"condition":"flat","geometry":geometry(name),
            "cases":[asdict(case) for case in cases_for(name)]} for name in TERRAINS},
        reset_seeds=[SEED_START],episodes_per_policy=5,episodes_per_policy_condition={"flat":5},
        policies=list(EXPORT_DIRS if export_dirs is None else export_dirs),conditions=["flat"],
        selection_only=False,qualification=False,automatic_selection=False,
        limitations=["One seed, five envs, native RTX4070 Ti; not historical Isaac multi-actor RNG-slot replay",
                     "No DDS bridge in this live PhysX audit; target guard counted without changing actor targets",
                     "No training, hardware actuation or policy promotion"])
    return result
