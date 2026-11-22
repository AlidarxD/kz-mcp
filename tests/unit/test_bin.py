import pytest

from kz_mcp.validation.bin import InvalidBinError, checksum, is_valid_checksum, validate_bin


@pytest.mark.parametrize(
    "value", ["000740000728", "160340026203", "0007 4000 0728", "000740-000728"]
)
def test_valid_bins(value):
    number, entity = validate_bin(value)
    assert len(number) == 12 and entity == "resident_legal_entity"


def test_second_weight_set_is_used_when_first_gives_10():
    w1, w2 = range(1, 12), [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]
    prefixes = (f"{n:011d}" for n in range(10**10, 10**10 + 5000))
    first_is_10 = [
        p for p in prefixes if sum(int(d) * w for d, w in zip(p, w1, strict=True)) % 11 == 10
    ]
    assert first_is_10
    for prefix in first_is_10:
        second = sum(int(d) * w for d, w in zip(prefix, w2, strict=True)) % 11
        assert checksum(prefix) == (None if second == 10 else second)
    assert any(checksum(p) is None for p in first_is_10)  # never-issued numbers exist
    p = next(p for p in first_is_10 if checksum(p) is not None)
    assert is_valid_checksum(p + str(checksum(p)))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("00074000072", "12 digits"),
        ("0007400007280", "12 digits"),
        ("00074000072a", "12 digits"),
        ("000740000729", "checksum"),
        ("900101300123", "checksum"),
    ],
)
def test_invalid_bins(value, message):
    with pytest.raises(InvalidBinError, match=message):
        validate_bin(value)


def test_iin_of_a_person_is_rejected():
    # birth date 900101, century/sex digit 3: a valid IIN, not a BIN
    prefix = "90010130012"
    control = checksum(prefix)
    assert control is not None
    with pytest.raises(InvalidBinError, match="IIN"):
        validate_bin(prefix + str(control))
