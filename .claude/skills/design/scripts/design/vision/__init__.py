"""macOS Vision through PyObjC, handed back as numpy arrays in the upright image's top-left pixel coordinates.

Everything Vision owns stays in here: which requests to make and how, pixel-buffer formats and their padded rows, reading a buffer only while it is locked and copying it out, normalised bottom-left coordinates, the low-resolution maps that have to be stretched to the image. Callers get a Scene of numpy arrays and plain tuples.
"""

from __future__ import annotations

import math
import platform
import sys
from dataclasses import dataclass

import numpy as np
from PIL import Image

from design.errors import Unavailable

LANDMARKS = ("faceContour", "leftEye", "rightEye", "leftEyebrow", "rightEyebrow", "leftPupil", "rightPupil", "nose", "noseCrest", "medianLine", "outerLips", "innerLips")

Box = tuple[float, float, float, float]  # x, y, w, h in pixels, top-left origin, inside the image


@dataclass
class Face:
    box: Box
    landmarks: dict[str, list[tuple[float, float]]]
    roll: float | None  # degrees, as Vision estimates them
    yaw: float | None
    pitch: float | None
    confidence: float


@dataclass
class Scene:
    person: np.ndarray  # uint8 H×W alpha of every person (accurate segmentation, bilinear)
    people: np.ndarray  # uint8 H×W: 0 background, 1..n one label per person, numbered left to right (nearest, so labels stay labels)
    people_count: int
    subject: np.ndarray  # uint8 H×W alpha of foreground objects, people included
    subject_count: int
    saliency: np.ndarray  # float32 H×W attention as Vision gives it (0..1)
    attention: list[tuple[Box, float]]  # salient boxes with confidence
    faces: list[Face]  # largest first
    cell: float  # image pixels per cell of the coarse maps behind people and subject


def available() -> tuple[bool, str]:
    """Whether macOS Vision can run here, and why not."""
    try:
        _frameworks()
    except Unavailable as exc:
        return False, exc.message
    return True, f"macOS {platform.mac_ver()[0]}"


def run(rgb: np.ndarray) -> Scene:
    """Analyse an upright 8-bit sRGB image (H×W×3)."""
    Vision, Quartz, objc = _frameworks()
    H, W = rgb.shape[:2]
    with objc.autorelease_pool():
        image = _cgimage(Quartz, rgb)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
        seg = Vision.VNGeneratePersonSegmentationRequest.alloc().initWithCompletionHandler_(None)
        seg.setQualityLevel_(Vision.VNGeneratePersonSegmentationRequestQualityLevelAccurate)
        inst = Vision.VNGeneratePersonInstanceMaskRequest.alloc().initWithCompletionHandler_(None)
        fg = Vision.VNGenerateForegroundInstanceMaskRequest.alloc().initWithCompletionHandler_(None)
        rects = Vision.VNDetectFaceRectanglesRequest.alloc().initWithCompletionHandler_(None)
        sal = Vision.VNGenerateAttentionBasedSaliencyImageRequest.alloc().initWithCompletionHandler_(None)
        ok, err = handler.performRequests_error_([seg, inst, fg, rects, sal], None)
        if not ok:
            raise Unavailable(f"the Vision requests failed: {err}")
        # Landmarks on the rectangles already found: the landmarks request alone finds fewer faces in a crowd.
        found = list(rects.results() or [])
        marks = Vision.VNDetectFaceLandmarksRequest.alloc().initWithCompletionHandler_(None)
        marks.setInputFaceObservations_(found)
        if found:
            ok, err = handler.performRequests_error_([marks], None)
            if not ok:
                raise Unavailable(f"the Vision face landmarks request failed: {err}")

        person = _stretch(_read(Quartz, seg.results()[0].pixelBuffer()), W, H, Image.BILINEAR)
        people, people_count, cell = _labels(Quartz, inst.results(), W, H)
        subject, subject_count = _foreground(Quartz, fg.results(), W, H)
        sal_obs = sal.results()[0]
        saliency = _stretch(_read(Quartz, sal_obs.pixelBuffer()), W, H, Image.BILINEAR)
        attention = [(_box(o.boundingBox(), W, H), float(o.confidence())) for o in (sal_obs.salientObjects() or [])]
        faces = [f for f in (_face(o, W, H) for o in (marks.results() or found)) if f.box[2] >= 1 and f.box[3] >= 1]  # wholly outside the frame
    faces.sort(key=lambda f: f.box[2] * f.box[3], reverse=True)
    return Scene(person, people, people_count, subject, subject_count, saliency, attention, faces, cell)


def _frameworks():
    if sys.platform != "darwin":
        raise Unavailable("macOS Vision runs only on macOS")
    major = int((platform.mac_ver()[0] or "0").split(".")[0])
    if major < 14:
        raise Unavailable(f"macOS 14 or later is needed (person instance and foreground subject requests); this is {platform.mac_ver()[0]}")
    try:
        import objc
        import Quartz
        import Vision
    except ImportError as e:
        raise Unavailable(f"PyObjC Vision could not be imported: {e}") from e
    return Vision, Quartz, objc


def _cgimage(Quartz, rgb: np.ndarray):
    H, W = rgb.shape[:2]
    rgbx = np.empty((H, W, 4), np.uint8)
    rgbx[..., :3] = rgb
    rgbx[..., 3] = 255
    provider = Quartz.CGDataProviderCreateWithCFData(rgbx.tobytes())
    space = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    return Quartz.CGImageCreate(W, H, 8, 32, W * 4, space, Quartz.kCGImageAlphaNoneSkipLast, provider, None, False, Quartz.kCGRenderingIntentDefault)


def _read(Quartz, buf) -> np.ndarray:
    """A one-component pixel buffer as a fresh array: rows are padded to bytes-per-row, and the memory is only valid while locked."""
    formats = {Quartz.kCVPixelFormatType_OneComponent8: np.uint8, Quartz.kCVPixelFormatType_OneComponent32Float: np.float32}
    fmt = Quartz.CVPixelBufferGetPixelFormatType(buf)
    if fmt not in formats:
        raise Unavailable(f"Vision returned an unexpected pixel format: {fmt.to_bytes(4, 'big')!r}")
    dtype = np.dtype(formats[fmt])
    Quartz.CVPixelBufferLockBaseAddress(buf, Quartz.kCVPixelBufferLock_ReadOnly)
    try:
        w, h = Quartz.CVPixelBufferGetWidth(buf), Quartz.CVPixelBufferGetHeight(buf)
        stride = Quartz.CVPixelBufferGetBytesPerRow(buf)
        raw = Quartz.CVPixelBufferGetBaseAddress(buf).as_buffer(stride * h)
        rows = np.frombuffer(raw, np.uint8).reshape(h, stride)[:, : w * dtype.itemsize]
        return np.ascontiguousarray(rows).view(dtype).reshape(h, w).copy()
    finally:
        Quartz.CVPixelBufferUnlockBaseAddress(buf, Quartz.kCVPixelBufferLock_ReadOnly)


def _stretch(a: np.ndarray, W: int, H: int, resample) -> np.ndarray:
    """A Vision map covers the whole image whatever its own aspect, so it is stretched to W×H."""
    if a.dtype == np.float32:
        return np.asarray(Image.fromarray(a, "F").resize((W, H), resample), dtype=np.float32)
    return np.asarray(Image.fromarray(a, "L").resize((W, H), resample))


def _labels(Quartz, results, W: int, H: int) -> tuple[np.ndarray, int, float]:
    if not results or results[0].allInstances().count() == 0:
        return np.zeros((H, W), np.uint8), 0, 1.0
    small = _read(Quartz, results[0].instanceMask())
    ids = [int(i) for i in np.unique(small) if i]
    order = sorted(ids, key=lambda i: np.nonzero(small == i)[1].mean())  # left to right
    lut = np.zeros(256, np.uint8)
    for n, i in enumerate(order, 1):
        lut[i] = n
    return _stretch(lut[small], W, H, Image.NEAREST), len(order), W / small.shape[1]


def _foreground(Quartz, results, W: int, H: int) -> tuple[np.ndarray, int]:
    if not results or results[0].allInstances().count() == 0:
        return np.zeros((H, W), np.uint8), 0
    small = _read(Quartz, results[0].instanceMask())
    return _stretch(np.where(small > 0, 255, 0).astype(np.uint8), W, H, Image.BILINEAR), int(results[0].allInstances().count())


def _box(bb, W: int, H: int) -> Box:
    """Top-left pixels, clipped to the image: Vision reports a face cut by the frame whole, and a negative x would make slicing wrap around."""
    x0, y0 = bb.origin.x * W, (1 - bb.origin.y - bb.size.height) * H
    x1, y1 = x0 + bb.size.width * W, y0 + bb.size.height * H
    x0, x1 = min(max(x0, 0.0), float(W)), min(max(x1, 0.0), float(W))
    y0, y1 = min(max(y0, 0.0), float(H)), min(max(y1, 0.0), float(H))
    return (x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))


def _face(o, W: int, H: int) -> Face:
    landmarks = {}
    lm = o.landmarks()
    if lm is not None:
        for name in LANDMARKS:
            region = getattr(lm, name)()
            if region is None or region.pointCount() == 0:
                continue
            pts = region.pointsInImageOfSize_((W, H))
            landmarks[name] = [(round(float(pts[i].x), 1), round(H - float(pts[i].y), 1)) for i in range(region.pointCount())]

    def angle(get):
        v = get() if get is not None else None
        return round(math.degrees(float(v)), 1) if v is not None else None

    return Face(_box(o.boundingBox(), W, H), landmarks, angle(getattr(o, "roll", None)), angle(getattr(o, "yaw", None)), angle(getattr(o, "pitch", None)), float(o.confidence()))
