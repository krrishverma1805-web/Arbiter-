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


def test_calibration_persists_and_reloads_and_shapes_matching(tmp_path):
    """A fitted recalibration map, persisted per spec hash, is loaded by the next
    run and pulls the matcher's P(match) toward observed accuracy (docs/28 §1.2)."""
    from arbiter_engine.events.store import EventStore
    from arbiter_engine.match.fellegi_sunter import FSModel
    from arbiter_engine.match.fs_store import load_calibration, persist_calibration

    store = EventStore("sqlite://")
    # a spread of over-confident predictions across several buckets
    preds = (
        [(0.95, True)] * 6
        + [(0.95, False)] * 4
        + [(0.75, True)] * 5
        + [(0.75, False)] * 5
        + [(0.55, True)] * 3
        + [(0.55, False)] * 7
    )
    report = calibrate(preds)
    assert report.recalibration and len(report.recalibration) >= 2

    ok = persist_calibration(
        store,
        "r1",
        "spec_abc",
        list(report.recalibration),
        n_samples=report.n,
        ece_before=report.ece,
    )
    assert ok is True
    assert persist_calibration(store, "r1", "spec_abc", [], n_samples=1, ece_before=0.0) is False

    loaded = load_calibration(store, "spec_abc")
    assert len(loaded) == len(report.recalibration)
    for (lx, ly), (rx, ry) in zip(loaded, report.recalibration, strict=True):
        assert abs(lx - rx) < 1e-5 and abs(ly - ry) < 1e-5
    assert load_calibration(store, "other_spec") == []

    # the loaded map, applied by FSModel, drags a high raw P(match) toward accuracy
    plain = FSModel()
    calibrated = FSModel(calibration=loaded)
    raw = plain.probability(6.0, prior=0.1)
    adj = calibrated.probability(6.0, prior=0.1)
    assert adj <= raw + 1e-9
