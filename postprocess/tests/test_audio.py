"""Pure-logic unit tests for the normalize stage (no audio file or ASR needed)."""

import numpy as np

from postprocess.audio import downmix_mono, peak_normalize, resample


def test_downmix_averages_channels():
    stereo = np.array([[1.0, 3.0], [2.0, 4.0]], dtype=np.float32)  # (frames, ch)
    mono = downmix_mono(stereo)
    assert mono.shape == (2,)
    np.testing.assert_allclose(mono, [2.0, 3.0])


def test_downmix_passes_through_mono():
    mono = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    np.testing.assert_array_equal(downmix_mono(mono), mono)


def test_resample_changes_length_by_ratio():
    sr, target = 48000, 16000
    x = np.random.default_rng(0).standard_normal(48000).astype(np.float32)  # 1 second
    y = resample(x, sr, target)
    # 1 second's worth becomes roughly 16k samples (allowing for polyphase-filter rounding)
    assert abs(len(y) - 16000) <= 2


def test_resample_noop_when_same_rate():
    x = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    y = resample(x, 16000, 16000)
    np.testing.assert_array_equal(y, x)


def test_peak_normalize_scales_to_target_peak():
    x = np.array([0.1, -0.2, 0.05], dtype=np.float32)
    y = peak_normalize(x, target_peak=0.95)
    assert np.isclose(np.max(np.abs(y)), 0.95, atol=1e-6)


def test_peak_normalize_leaves_near_silence_untouched():
    x = np.zeros(100, dtype=np.float32)
    y = peak_normalize(x)
    np.testing.assert_array_equal(y, x)
