"""Independent local job CLI. The HTTP dashboard is an optional reader."""
import argparse
import json
from job_manager import list_jobs, stop_job
from process_client import submit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    start=sub.add_parser('start')
    start.add_argument('kind',choices=('tests','train','evaluate','compare','stair_curriculum','stair_comparison_1350',
                                       'short_flight','short_flight_preflight'))
    start.add_argument('--updates',type=int,default=100)
    start.add_argument('--num-envs',type=int,default=4096)
    start.add_argument('--policy',default='24650')
    start.add_argument('--no-monitor',action='store_true')
    stop=sub.add_parser('stop');stop.add_argument('id')
    sub.add_parser('status')
    args=parser.parse_args()
    if args.action=='start':
        result=submit({'kind':args.kind,'updates':args.updates,'num_envs':args.num_envs,'policy':args.policy},
                      open_monitor=not args.no_monitor)
    elif args.action=='stop':result=stop_job(args.id)
    else:result=list_jobs()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
