import pytest
from wavelab.quantity_presets import QUANTITY_PRESETS, QuantityLibrary, conversion_factor


def test_required_presets():
    assert len(QUANTITY_PRESETS) == 36
    assert QUANTITY_PRESETS["voltage"].units[:3] == ("kV","V","mV")
    assert QUANTITY_PRESETS["current"].units[:3] == ("kA","A","mA")
    assert QUANTITY_PRESETS["active_power"].units == ("MW","kW","W","pu")
    assert QUANTITY_PRESETS["dc_link_voltage"].zh == "直流母线电压"
    assert len({QUANTITY_PRESETS[q].dimension for q in ("active_power","reactive_power","apparent_power")}) == 3


def test_custom_and_recent_are_local_preferences(tmp_path):
    library = QuantityLibrary(tmp_path)
    identity = library.add_custom("自定义量","User quantity","arb")
    library.remember(identity,"arb")
    restored = QuantityLibrary(tmp_path)
    assert restored.presets()[identity].default_unit == "arb"
    assert restored.recent() == [dict(preset_id=identity,unit="arb")]
    for unit in ("V","kV","mV","pu"):
        restored.remember("voltage",unit)
    restored.remember("voltage","V")
    assert restored.recent()[0] == dict(preset_id="voltage",unit="V")
    assert len(restored.recent()) == 5


@pytest.mark.parametrize("a,b,f",[("V","kV",.001),("kA","A",1000),("W","MW",1e-6),("s","μs",1e6)])
def test_registry_factors(a,b,f):
    assert conversion_factor(a,b) == pytest.approx(f)


@pytest.mark.parametrize("a,b",[("V","A"),("kV","pu"),("V","%"),("pu","%"),("W","var")])
def test_undefined_or_cross_quantity_conversion_rejected(a,b):
    with pytest.raises(ValueError): conversion_factor(a,b)
