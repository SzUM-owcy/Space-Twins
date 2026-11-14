import numpy as np
import pandas as pd
import pytest

from config import RECORD_COLUMNS
from src.contracts import validate_records

FAKE = "data/fake/{}_index_fake.csv"


@pytest.fixture
def good() -> pd.DataFrame:
    return pd.read_csv(FAKE.format("earth"))


def test_fake_csvs_valid(good):
    validate_records(good)
    validate_records(pd.read_csv(FAKE.format("moon")))
    assert len(good) >= 100 and good["region"].nunique() == 15


def test_wrong_columns_order(good):
    with pytest.raises(ValueError):
        validate_records(good[RECORD_COLUMNS[::-1]])


def test_nan(good):
    good.loc[0, "slope_p50"] = np.nan
    with pytest.raises(ValueError):
        validate_records(good)


def test_duplicate_id(good):
    good.loc[1, "patch_id"] = good.loc[0, "patch_id"]
    with pytest.raises(ValueError):
        validate_records(good)


def test_bad_source_and_lon(good):
    bad = good.copy()
    bad.loc[0, "source"] = "SRTM"
    with pytest.raises(ValueError):
        validate_records(bad)
    good.loc[0, "center_lon"] = 190
    with pytest.raises(ValueError):
        validate_records(good)
