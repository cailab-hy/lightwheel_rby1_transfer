"""Convert only locally authored asset paths; never flatten or edit dependencies."""
import os
from pathlib import Path
import project_paths as paths

def make_layer_portable(layer):
    from pxr import UsdUtils
    base = Path(layer.realPath).parent
    def remap(asset):
        if not asset or not os.path.isabs(asset):
            return asset
        for source, target in [(paths.LIGHTWHEEL_CACHE, paths.ASSET_LINKS / 'lightwheel'), (paths.RBY_SIM, paths.ASSET_LINKS / 'rby1'), (paths.ROOT, paths.ROOT)]:
            try:
                suffix = Path(asset).relative_to(source)
            except ValueError:
                continue
            return os.path.relpath(target / suffix, base)
        raise ValueError(f'Unconfigured absolute USD asset: {asset}')
    UsdUtils.ModifyAssetPaths(layer, remap)
