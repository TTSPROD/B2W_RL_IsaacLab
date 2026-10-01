"""Shared same-slot evaluation orchestration and validated combined summaries."""
import importlib
from run_support import ROOT,read_json,write_json,sha256,utc_now


def combine(summaries):
    if not summaries:
        raise ValueError('No validated summaries')
    first=next(iter(summaries.values()))
    ignored={'policies','exports','policy_map_sha256'}
    template={k:v for k,v in first['plan'].items() if k not in ignored}
    for policy,summary in summaries.items():
        if summary['plan']['policies'] not in ([policy],[int(policy)] if policy.isdigit() else []):
            raise ValueError('Foreign/multiple actor in isolated result')
        if ({k:v for k,v in summary['plan'].items() if k not in ignored}!=template
                or summary['runtime']!=first['runtime'] or summary['compiled_model']!=first['compiled_model']):
            raise ValueError('Isolated comparison protocol/runtime/model drift')
    result={k:first[k] for k in ('schema','runtime','compiled_model','qualification','hardware_approval')}
    result.update(plan={**template,'policies':list(summaries),
                       'exports':{p:s['plan']['exports'][p] for p,s in summaries.items()}},
                  derived_summary=True,comparison_layout='one actor per fresh process, identical slots',
                  candidate_recommendation=None,ranking=list(summaries),
                  input_sha256={k:v for s in summaries.values() for k,v in s['input_sha256'].items()})
    for key in ('overall','conditions','cells','all_cells_pass'):
        result[key]={p:s[key][p] for p,s in summaries.items()}
    return result


class IsolatedEvaluation:
    def __init__(self, base, module_name, policies, extra_sources=()):
        self.base,self.module,self.policies,self.extra=base,module_name,list(map(str,policies)),extra_sources
        self.protocol=importlib.import_module(module_name)
        self.summaries={}
        self.base.mkdir(parents=True,exist_ok=False)
        write_json(base/'comparison_plan.json',{'policies':self.policies,'module':module_name,
            'layout':'one actor per fresh process; fixed case/reset order',
            'episodes_per_actor':sum(len(self.protocol.cases_for(t)) for t in self.protocol.TERRAINS)*self.protocol.SEEDS})

    def evaluate(self,policy,export):
        from run_tracking_pilot import freeze
        from run_core_locomotion_eval import run
        from summarize_locomotion import summarize_run
        p=str(policy)
        if p not in self.policies or p in self.summaries:
            raise ValueError('Undeclared/duplicate isolated actor')
        folder=self.base/p
        freeze(folder,{policy:export},self.module,extra_sources=self.extra)
        prior=[f'{actor}/{t}' for actor in self.summaries for t in self.protocol.TERRAINS]
        def progress(current):
            write_json(self.base/'evaluation_progress.json',{
                'status':'failed' if current['status']=='failed' else 'running',
                'total_jobs':len(self.policies)*len(self.protocol.TERRAINS),
                'completed':prior+[f'{p}/{t}' for t in current['completed']],
                'active':[f'{p}/{t}' for t in current['active']],
                'failures':current['failures'],'updated':utc_now()})
        run(folder,self.module,max_parallel=1,on_progress=progress)
        self.summaries[p]=summarize_run(folder)
        combined=combine(self.summaries)
        combined['partial']=len(self.summaries)!=len(self.policies)
        write_json(self.base/'analysis/summary.json',combined)
        if not combined['partial']:
            state=read_json(self.base/'evaluation_progress.json')
            state.update(status='completed',active=[],updated=utc_now())
            write_json(self.base/'evaluation_progress.json',state)
        return self.summaries[p]

    def records(self):
        if len(self.summaries)!=len(self.policies):
            raise ValueError('Incomplete isolated comparison')
        from summarize_locomotion import validate_terrain
        records=[]
        for p,summary in self.summaries.items():
            for terrain in self.protocol.TERRAINS:
                records.extend(validate_terrain(self.base/p,terrain,summary['plan'])['records'])
        return records
