"""Contact-filter repair: target the collider child, not its terrain Xform."""
from pathlib import Path

path = Path(__file__).with_name('replay57_isaac.py')
source = path.read_text(encoding='utf-8')
assert source.count("'/World/ground/terrain'") == 2
source = source.replace("'/World/ground/terrain'","'/World/ground/terrain/mesh'")
source = source.replace('isaac_nominal','isaac_contactmesh')
exec(compile(source,str(path),'exec'))
