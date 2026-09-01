from arbiter_engine.bench.calibration import _isotonic, calibrate


def test_perfectly_calibrated_has_low_ece():
    # confidence == accuracy in every bucket
    preds = [(0.9, True)] * 9 + [(0.9, False)] * 1 + [(0.5, True)] * 5 + [(0.5, False)] * 5
    r = calibrate(preds)
    assert r.ece < 0.05
    assert r.to_dict()["well_calibrated"] is True
    assert r.applied is False


def test_overconfident_triggers_recalibration():
    # everything predicted at 0.95 but only 60% correct
    preds = [(0.95, True)] * 6 + [(0.95, False)] * 4
    r = calibrate(preds)
    assert r.ece > 0.05
    assert r.applied is True
    assert r.recalibration  # a monotonic map was produced


def test_isotonic_is_monotonic():
    out = _isotonic([(0.2, 0.5), (0.4, 0.3), (0.6, 0.9), (0.8, 0.7)])
    ys = [y for _, y in out]
    assert ys == sorted(ys)


def test_empty_predictions():
    r = calibrate([])
    assert r.n == 0
    assert r.ece == 0.0
