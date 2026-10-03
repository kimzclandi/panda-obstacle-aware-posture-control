import pybullet as p, pybullet_data as pd
import numpy as np
import itertools, json, pathlib, hashlib, importlib.metadata, time, argparse
parser=argparse.ArgumentParser()
parser.add_argument("--output",type=pathlib.Path,required=True)
args=parser.parse_args()
if args.output.exists(): raise FileExistsError(args.output)
p.connect(p.DIRECT)
p.setAdditionalSearchPath(pd.getDataPath())
r=p.loadURDF('franka_panda/panda.urdf', useFixedBase=True, flags=p.URDF_USE_SELF_COLLISION)
info=[p.getJointInfo(r,j) for j in range(p.getNumJoints(r))]
names={-1:'panda_link0', **{i:i0[12].decode() for i,i0 in enumerate(info)}}
parents={i:x[16] for i,x in enumerate(info)}
link_by_name={v:k for k,v in names.items()}
def link_pair(a,b): return tuple(sorted((link_by_name[a],link_by_name[b])))
shape_links=[i for i in names if p.getCollisionShapeData(r,i)]
pairs=list(itertools.combinations(shape_links,2))
adjacent={tuple(sorted((i,parents[i]))) for i in parents}
fixed_structure={link_pair('panda_link7','panda_hand')}
exclude=adjacent|fixed_structure
checked=[ij for ij in pairs if ij not in exclude]
arm=[j for j,x in enumerate(info) if x[1].decode().startswith('panda_joint') and x[2]==p.JOINT_REVOLUTE]
fingers=[j for j,x in enumerate(info) if x[2]==p.JOINT_PRISMATIC]
lo=np.array([info[j][8] for j in arm]); hi=np.array([info[j][9] for j in arm])
qhome=np.array([0,-np.pi/4,0,-3*np.pi/4,0,np.pi/2,np.pi/4])
def reset(q):
    for j,v in zip(arm,q): p.resetJointState(r,j,v)
    for j in fingers: p.resetJointState(r,j,.02)
    p.performCollisionDetection()
def dist(pair):
    cp=p.getClosestPoints(r,r,distance=10.,linkIndexA=pair[0],linkIndexB=pair[1])
    return min(x[8] for x in cp) if cp else None
reset(qhome)
home_all={f'{names[a]} / {names[b]}':dist((a,b)) for a,b in pairs}
positive={}; first=None; t=time.perf_counter()
rng=np.random.default_rng(4401)
for k in range(1500):
    q=rng.uniform(lo+.04,hi-.04)
    reset(q)
    for pair in checked:
        d=dist(pair)
        if d is not None and d < -.005 and pair not in positive:
            positive[pair]={'pair':[names[i] for i in pair], 'indices':list(pair),'distance_m':d,'q_rad':q.tolist(),'sample':k}
    if link_pair('panda_link5','panda_link7') in positive and any(link_by_name['panda_hand'] in x for x in positive) and k>100: break
samples=k+1
# Query retained self-pair after filtering each excluded collision pair.
for pair in exclude: p.setCollisionFilterPair(r,r,*pair,0)
if positive:
    first=next((v for ij,v in positive.items() if link_by_name['panda_hand'] in ij),next(iter(positive.values())))
    reset(first['q_rad'])
    first['getClosestPoints_after_filter_m']=dist(tuple(first['indices']))
    first['excluded_fixed_pair_closest_points_m']=dist(link_pair('panda_link7','panda_hand'))
    first['contacts_after_filter']=[{'pair':[names[c[3]],names[c[4]]],'distance_m':c[8]} for c in p.getContactPoints(r,r)]
# Spherical penetration at actual collision geometry AABB center in home posture.
reset(qhome)
obstacle=[]
for link_name in ['panda_link3','panda_hand','panda_leftfinger','panda_rightfinger']:
    li=link_by_name[link_name]
    aabb=p.getAABB(r,li)
    center=np.mean(aabb,axis=0)
    shape=p.createCollisionShape(p.GEOM_SPHERE,radius=.04)
    sphere=p.createMultiBody(baseMass=0,baseCollisionShapeIndex=shape,basePosition=center)
    p.performCollisionDetection()
    cp=p.getClosestPoints(r,sphere,distance=0,linkIndexA=li)
    obstacle.append({'link':names[li],'link_index':li,'sphere_center_m':center.tolist(),'radius_m':.04,'min_distance_m':min([x[8] for x in cp],default=None),'all_contact_links':sorted({names[x[3]] for x in p.getContactPoints(r,sphere)})})
    p.removeBody(sphere)
urdf=pathlib.Path(pd.getDataPath())/'franka_panda/panda.urdf'
out={'purpose':'Static diagnostic only; resets are not rollouts or feasible dynamic witnesses.','pybullet':importlib.metadata.version('pybullet'),'urdf_sha256':hashlib.sha256(urdf.read_bytes()).hexdigest(),'joint_information':[{'joint_index':j,'joint_name':x[1].decode(),'type':x[2],'qIndex':x[3],'uIndex':x[4],'link_name':x[12].decode(),'parent_index':x[16],'lower':x[8],'upper':x[9]} for j,x in enumerate(info)],'shape_links':{i:names[i] for i in shape_links},'excluded_pairs':[{'pair':[names[i] for i in ij],'indices':list(ij)} for ij in sorted(exclude) if ij in pairs],'checked_pairs':[[names[i] for i in ij] for ij in checked],'home_q_rad':qhome.tolist(),'finger_q_m':.02,'home_pair_distances_m':home_all,'samples':samples,'sample_seed':4401,'sampling_time_s':time.perf_counter()-t,'positive_pairs':list(positive.values()),'sphere_diagnostics':obstacle}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'samples':samples,'checked_pairs':len(checked),'home_negative_checked':{k:v for k,v in home_all.items() if v is not None and v < -1e-5 and k in [f'{names[a]} / {names[b]}' for a,b in checked]},'positive_pairs':list(positive.values()),'sphere_diagnostics':obstacle},indent=2))
p.disconnect()
