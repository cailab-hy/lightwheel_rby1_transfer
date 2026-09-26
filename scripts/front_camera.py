"""Shared front view used by the task screenshots and initial GUI viewport."""
from pxr import Gf, UsdGeom

CAMERA_PATH = '/World/FrontPreviewCamera'
EYE = (2.44, -4.0, 2.15)
TARGET = (2.44, -1.90, 1.02)

def author_front_camera(stage):
    camera = UsdGeom.Camera.Define(stage, CAMERA_PATH)
    camera.CreateProjectionAttr().Set(UsdGeom.Tokens.perspective)
    camera.CreateFocalLengthAttr().Set(34)
    camera.CreateHorizontalApertureAttr().Set(36)
    camera.CreateVerticalApertureAttr().Set(22.5)
    camera.CreateClippingRangeAttr().Set(Gf.Vec2f(.01, 100))
    transform = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*EYE), Gf.Vec3d(*TARGET), Gf.Vec3d(0, 0, 1)).GetInverse()
    xform = UsdGeom.Xformable(camera)
    xform.ClearXformOpOrder()
    xform.MakeMatrixXform().Set(transform)
    stage.SetMetadataByDictKey('customLayerData', 'cameraSettings:boundCamera', CAMERA_PATH)
    return camera

def activate_front_camera():
    from omni.kit.viewport.utility import get_active_viewport
    viewport = get_active_viewport()
    if viewport is not None:
        viewport.camera_path = CAMERA_PATH
        assert str(viewport.camera_path) == CAMERA_PATH
        print('DEFAULT_VIEW', CAMERA_PATH, flush=True)
