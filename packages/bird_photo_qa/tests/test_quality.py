"""Quality-gate unit tests; does not load the detector."""

from __future__ import annotations

import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from bird_photo_qa import quality as Q


def _pink_noise(size: int = 256, beta: float = 2.0, seed: int = 0) -> np.ndarray:
    """1/f 噪声，近似照片里的自然频谱。"""
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.fftfreq(size)[None, :]
    freq = np.sqrt(fx * fx + fy * fy)
    freq[0, 0] = 1.0
    spec = rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))
    spec = spec / (freq ** (beta / 2.0))
    spec[0, 0] = 0
    img = np.fft.ifft2(spec).real
    img = (img - img.min()) / (img.max() - img.min() + 1e-9) * 255.0
    return img.astype(np.float32)


def _checkerboard(size: int = 256, cell: int = 8) -> Image.Image:
    arr = np.zeros((size, size), dtype=np.uint8)
    for row in range(0, size, cell):
        for col in range(0, size, cell):
            if ((row // cell) + (col // cell)) % 2 == 0:
                arr[row : row + cell, col : col + cell] = 255
    return Image.fromarray(arr, mode="L")


class QualityMetricsTests(unittest.TestCase):
    def test_laplacian_sharp_beats_blurred(self) -> None:
        sharp = np.asarray(_checkerboard(), dtype=np.float32)
        blurry = np.asarray(
            _checkerboard().filter(ImageFilter.GaussianBlur(radius=4)),
            dtype=np.float32,
        )
        self.assertGreater(Q.laplacian_variance(sharp), Q.laplacian_variance(blurry) * 3)

    def test_crete_blur_higher_when_smoothed(self) -> None:
        sharp = _checkerboard()
        blurry = sharp.filter(ImageFilter.GaussianBlur(radius=5))
        self.assertGreater(Q.crete_blur(blurry), Q.crete_blur(sharp))

    def test_fft_mid_high_ratio_flags_defocus_plus_grain(self) -> None:
        """Laplacian 会被放大噪声抬高；中频/高频比仍能标出失焦放大图。"""
        sharp = _pink_noise()
        soft = Image.fromarray(sharp.astype(np.uint8)).resize((64, 64), Image.BILINEAR)
        upscaled = np.asarray(soft.resize((256, 256), Image.BILINEAR), dtype=np.float32)
        grain = np.random.default_rng(1).normal(0, 50, (256, 256))
        grain_img = Image.fromarray(np.clip(grain + 128, 0, 255).astype(np.uint8))
        grain = np.asarray(grain_img.filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float32) - 128
        mushy = np.clip(upscaled + grain, 0, 255)
        self.assertLess(Q.fft_mid_high_ratio(sharp), 8.0)
        self.assertGreaterEqual(Q.fft_mid_high_ratio(mushy), 8.0)
        self.assertGreaterEqual(Q.laplacian_variance(mushy), 70.0)

    def test_area_frac(self) -> None:
        self.assertAlmostEqual(Q._area_frac([0.1, 0.1, 0.3, 0.5]), 0.08, places=5)

    def test_crop_from_norm(self) -> None:
        img = Image.new("RGB", (100, 50), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((20, 10, 40, 30), fill=(255, 0, 0))
        crop = Q._crop_from_norm(img, [0.2, 0.2, 0.4, 0.6], pad=0)
        self.assertEqual(crop.size, (20, 20))


class FailReasonTests(unittest.TestCase):
    def test_skip_when_detector_failed(self) -> None:
        metrics = Q.QualityMetrics(detect_ok=False, detect_error="no torch")
        self.assertEqual(Q.quality_fail_reasons(metrics), [])

    def test_no_bird_box(self) -> None:
        metrics = Q.QualityMetrics(detect_ok=True, bird_n=0, bird_max=0.0)
        self.assertEqual(Q.quality_fail_reasons(metrics), ["quality_no_bird_box"])
        keep = Q.QualityThresholds(drop_if_no_bird=False)
        self.assertEqual(Q.quality_fail_reasons(metrics, keep), [])

    def test_small_bird(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.02,
            bird_score=0.9,
            crop_lap=400.0,
        )
        self.assertEqual(Q.quality_fail_reasons(metrics), ["quality_small_bird"])

    def test_small_bird_at_threshold_fails(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.025,
            bird_score=0.9,
            crop_lap=400.0,
        )
        self.assertEqual(Q.quality_fail_reasons(metrics), ["quality_small_bird"])

    def test_bird_just_over_min_frac_passes(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.03,
            bird_score=0.9,
            crop_lap=400.0,
        )
        self.assertEqual(Q.quality_fail_reasons(metrics), [])

    def test_large_sharp_bird_passes(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.32,
            bird_score=0.99,
            crop_lap=400.0,
            person_n=0,
        )
        self.assertEqual(Q.quality_fail_reasons(metrics), [])

    def test_blur_subject(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.4,
            crop_lap=20.0,
        )
        self.assertEqual(Q.quality_fail_reasons(metrics), ["quality_blur_subject"])
        off = Q.QualityThresholds(min_crop_lap=0)
        self.assertEqual(Q.quality_fail_reasons(metrics, off), [])

    def test_blur_spectrum_when_fft_ratio_high(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.38,
            crop_lap=189.0,
            crop_fft=9.91,
        )
        self.assertEqual(Q.quality_fail_reasons(metrics), ["quality_blur_spectrum"])
        off = Q.QualityThresholds(max_crop_fft=0)
        self.assertEqual(Q.quality_fail_reasons(metrics, off), [])

    def test_large_noisy_but_focused_bird_passes_fft(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.32,
            crop_lap=400.0,
            crop_fft=6.0,
        )
        self.assertEqual(Q.quality_fail_reasons(metrics), [])

    def test_people_scene(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.09,
            crop_lap=300.0,
            person_n=5,
            person_max=0.12,
        )
        self.assertIn("quality_people_scene", Q.quality_fail_reasons(metrics))

    def test_small_and_blur_both_reported(self) -> None:
        metrics = Q.QualityMetrics(
            detect_ok=True,
            bird_n=1,
            bird_max=0.02,
            crop_lap=10.0,
        )
        reasons = Q.quality_fail_reasons(metrics)
        self.assertEqual(reasons, ["quality_small_bird", "quality_blur_subject"])


if __name__ == "__main__":
    unittest.main()
