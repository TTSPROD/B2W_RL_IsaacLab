"""Launch the unchanged project evaluators in the pinned Linux container."""
import os
from pathlib import Path
import runpy
import sys
from isaaclab.app import AppLauncher
from isaac_compat import apply_pinned_urdf_importer_compatibility

original = AppLauncher.__init__
def initialize(self, launcher_args=None, **kwargs):
    options = dict(launcher_args or {})
    options['kit_args'] = '--ext-folder=/cache/exts --/app/extensions/registryEnabled=false --/app/settings/persistent=false'
    original(self, options, **kwargs)
    apply_pinned_urdf_importer_compatibility()
    import local_b2w_assets
    configure = local_b2w_assets.configure_b2w_env
    def isolated_assets(cfg):
        configure(cfg)
        cfg.scene.robot.spawn.usd_dir = f'/run-output/eval-usd/gpu{os.environ.get("CUDA_VISIBLE_DEVICES", "0")}'
        return cfg
    local_b2w_assets.configure_b2w_env = isolated_assets
AppLauncher.__init__ = initialize
script = Path(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, str(script.parent))
runpy.run_path(str(script), run_name='__main__')
