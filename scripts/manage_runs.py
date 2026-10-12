"""Independent local job CLI; every submitted run opens the external monitor."""
import argparse
import json
from job_manager import list_jobs, stop_job
from process_client import submit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    start=sub.add_parser('start')
    start.add_argument('kind',choices=('native_continuation','sim2sim_timing','sim2sim_pd_guard','sim2sim_armature','sim2sim_actuator','sim2sim_isaac','sim2sim_physics','sim2sim_faults','sim2sim','tests','train','evaluate','compare','gradient_audit','micro_sweep',
                                      'composite_probe','specialist_stage2','stair_curriculum',
                                      'specialist_repeat','axis_specialists','axis_specialists_stage2','lateral_curve',
                                      'axis_mixed_probe',
                                      'axis_endpoint_screen',
                                      'axis_robust_composite',
                                      'axis_endpoint_confirm',
                                      'axis_repeat3',
                                      'stair_comparison_1350','short_flight','short_flight_preflight'))
    start.add_argument('--updates',type=int,default=100)
    start.add_argument('--num-envs',type=int,default=4096)
    start.add_argument('--policy',default='24650')
    start.add_argument('--source-job')
    # Keep old command lines valid; this flag no longer suppresses monitoring.
    start.add_argument('--no-monitor',action='store_true',help=argparse.SUPPRESS)
    stop=sub.add_parser('stop');stop.add_argument('id')
    sub.add_parser('status')
    args=parser.parse_args()
    if args.action=='start':
        result=submit({'kind':args.kind,'updates':args.updates,'num_envs':args.num_envs,
                       'policy':args.policy,'source_job':args.source_job})
    elif args.action=='stop':result=stop_job(args.id)
    else:result=list_jobs()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
