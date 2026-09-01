import pytest
from arbiter_engine.money import MoneyParseError, format_minor, to_minor


@pytest.mark.parametrize(
    ("value", "scale", "expected"),
    [
        ("1000.00", "rupees_to_paise", 100000),
        ("1,234.56", "rupees_to_paise", 123456),
        ("0", "rupees_to_paise", 0),
        ("-194.70", "rupees_to_paise", -19470),
        ("80453000", "already_paise", 80453000),
        (824000, "already_paise", 824000),
    ],
)
def test_to_minor(value, scale, expected):
    assert to_minor(value, scale=scale) == expected


def test_to_minor_rejects_bool_and_garbage():
    with pytest.raises(MoneyParseError):
        to_minor(True)  # noqa: FBT003
    with pytest.raises(MoneyParseError):
        to_minor("not-a-number")


def test_half_up_rounding_is_exact():
    # 0.005 * 100 -> 0.5 -> rounds up to 1 paise, deterministically
    assert to_minor("0.005", scale="rupees_to_paise") == 1
    assert to_minor("2.675", scale="rupees_to_paise") == 268


@pytest.mark.parametrize(
    ("minor", "expected"),
    [
        (-19470, "-₹194.70"),
        (100000, "₹1,000.00"),
        (954200000, "₹95,42,000.00"),  # Indian grouping
        (0, "₹0.00"),
    ],
)
def test_format_minor(minor, expected):
    assert format_minor(minor) == expected
