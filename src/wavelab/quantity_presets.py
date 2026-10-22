"""Single source for electrical quantities, units and local preferences.

No waveform data, model calls or inferred physical mappings belong here.
"""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4


@dataclass(frozen=True)
class Unit:
    symbol: str
    dimension: str
    factor: float
    family: str


UNITS = {}


def _units(dimension, entries, family=None):
    for symbol, factor in entries:
        UNITS[symbol] = Unit(symbol, dimension, factor, family or dimension)


_units("voltage", [("kV",1e3),("V",1),("mV",1e-3)])
_units("current", [("kA",1e3),("A",1),("mA",1e-3)])
_units("active_power", [("MW",1e6),("kW",1e3),("W",1)])
_units("reactive_power", [("Mvar",1e6),("kvar",1e3),("var",1)])
_units("apparent_power", [("MVA",1e6),("kVA",1e3),("VA",1)])
_units("energy", [("J",1),("kJ",1e3),("MJ",1e6)], "joule")
_units("energy", [("Wh",1),("kWh",1e3),("MWh",1e6)], "watt_hour")
_units("time", [("s",1),("ms",1e-3),("μs",1e-6)])
_units("frequency", [("Hz",1),("kHz",1e3)])
_units("angular_frequency", [("rad/s",1)])
_units("phase_angle", [("rad",1)], "radian")
_units("phase_angle", [("°",1)], "degree")
_units("rocof", [("Hz/s",1)])
_units("resistance", [("Ω",1),("mΩ",1e-3),("kΩ",1e3)])
_units("inductance", [("H",1),("mH",1e-3),("μH",1e-6)])
_units("capacitance", [("F",1),("mF",1e-3),("μF",1e-6),("nF",1e-9)])
_units("temperature", [("°C",1)], "celsius")
_units("temperature", [("K",1)], "kelvin")
_units("dimensionless", [("1",1)], "dimensionless")
_units("relative", [("pu",1)], "pu")
_units("relative", [("%",1)], "percent")
for alias, canonical in {"℃":"°C", "µs":"μs", "us":"μs", "µH":"μH", "µF":"μF", "p.u.":"pu"}.items():
    UNITS[alias] = UNITS[canonical]


@dataclass(frozen=True)
class QuantityPreset:
    id: str
    zh: str
    en: str
    units: tuple[str, ...]
    default_unit: str
    category: str
    dimension: str


QUANTITY_PRESETS = {}


def _quantities(category, dimension, units, default, names):
    for identity, zh, en in names:
        QUANTITY_PRESETS[identity] = QuantityPreset(identity, zh, en, tuple(units), default, category, dimension)


_quantities("电压", "voltage", ("kV","V","mV","pu"), "kV", [
    ("voltage","电压","Voltage"),("dc_voltage","直流电压","DC Voltage"),
    ("ac_voltage","交流电压","AC Voltage"),("capacitor_voltage","电容电压","Capacitor Voltage"),
    ("arm_voltage","桥臂电压","Arm Voltage"),("dc_link_voltage","直流母线电压","DC-Link Voltage"),
    ("dq_voltage","dq轴电压","dq-Axis Voltage")])
_quantities("电流", "current", ("kA","A","mA","pu"), "kA", [
    ("current","电流","Current"),("ac_current","交流电流","AC Current"),
    ("dc_current","直流电流","DC Current"),("arm_current","桥臂电流","Arm Current"),
    ("circulating_current","环流","Circulating Current"),("differential_current","差动电流","Differential Current"),
    ("dq_current","dq轴电流","dq-Axis Current")])
for identity, zh, en, dimension, units in [
    ("active_power","有功功率","Active Power","active_power",("MW","kW","W","pu")),
    ("reactive_power","无功功率","Reactive Power","reactive_power",("Mvar","kvar","var","pu")),
    ("apparent_power","视在功率","Apparent Power","apparent_power",("MVA","kVA","VA","pu")),
    ("energy","能量","Energy","energy",("J","kJ","MJ","Wh","kWh","MWh"))]:
    _quantities("功率与能量", dimension, units, units[0], [(identity,zh,en)])
for identity, zh, en, dimension, units in [
    ("time","时间","Time","time",("s","ms","μs")),
    ("frequency","频率","Frequency","frequency",("Hz","kHz","pu")),
    ("angular_frequency","角频率","Angular Frequency","angular_frequency",("rad/s",)),
    ("phase_angle","相角","Phase Angle","phase_angle",("rad","°")),
    ("rocof","频率变化率","RoCoF","rocof",("Hz/s",))]:
    _quantities("控制与频率",dimension,units,units[0],[(identity,zh,en)])
_quantities("控制与频率", "dimensionless", ("1","pu","%"), "1", [
    ("modulation_index","调制比","Modulation Index"),("duty_cycle","占空比","Duty Cycle")])
_quantities("控制与频率", "dimensionless", ("%","1","pu"), "%", [
    ("thd","总谐波畸变率","THD"),("efficiency","效率","Efficiency"),
    ("voltage_unbalance","电压不平衡度","Voltage Unbalance"),("current_unbalance","电流不平衡度","Current Unbalance")])
for identity, zh, en, units in [
    ("resistance","电阻","Resistance",("Ω","mΩ","kΩ")),
    ("inductance","电感","Inductance",("H","mH","μH")),
    ("capacitance","电容","Capacitance",("F","mF","μF","nF")),
    ("temperature","温度","Temperature",("°C","K"))]:
    _quantities("电路参数",identity,units,units[0],[(identity,zh,en)])

# Additional channel choices share the existing registry and persistence model.
_quantities("电路参数", "resistance", ("Ω","mΩ","pu"), "Ω", [("impedance","阻抗","Impedance")])
_quantities("控制与频率", "relative", ("pu","1"), "pu", [("per_unit","标幺值","Per unit")])
_quantities("状态量", "state", (), "", [("switch_state","开关状态","Switch state")])
# Keep historical temperature units selectable while exposing the requested symbol.
q = QUANTITY_PRESETS["temperature"]
QUANTITY_PRESETS["temperature"] = QuantityPreset(q.id,q.zh,q.en,("℃","K","°C"),"℃",q.category,q.dimension)

COMMON_UNITS = ("kV","V","kA","A","MW","kW","Mvar","Hz","s","ms","pu","%")


def conversion_factor(source, target):
    if not source or not target:
        raise ValueError("请先确认源数据单位，再选择显示单位")
    if source == target:
        return 1.
    a, b = UNITS.get(source), UNITS.get(target)
    if not a or not b or a.family != b.family:
        raise ValueError(f"不能自动将 {source} 换算为 {target}；维度不兼容或缺少基准/明确定义")
    return a.factor / b.factor


def time_factor(unit):
    value = UNITS.get(unit)
    if not value or value.dimension != "time":
        raise ValueError("时间显示单位只支持 s / ms / μs")
    return 1. / value.factor


def validate_quantity_unit(quantity, unit):
    if not unit or not unit.strip():
        raise ValueError("请明确源数据单位")
    registered = UNITS.get(unit)
    if registered and unit not in quantity.units and registered.dimension != quantity.dimension:
        raise ValueError(f"{quantity.zh} 与单位 {unit} 不兼容")


_preference_lock = RLock()


class QuantityLibrary:
    """Application preferences, never copied into every FigureSpec."""
    def __init__(self, root):
        self.path = Path(root) / "quantity_preferences.json"

    def _load(self):
        if not self.path.exists():
            return dict(custom=[], recent=[])
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("custom"), list) or not isinstance(data.get("recent"), list):
            raise ValueError("物理量偏好文件损坏；未覆盖，请检查 quantity_preferences.json")
        return data

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
            os.replace(temporary,self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def presets(self):
        with _preference_lock:
            result = dict(QUANTITY_PRESETS)
            for row in self._load()["custom"]:
                q = QuantityPreset(**dict(row,units=tuple(row["units"])))
                if q.id in result:
                    raise ValueError("自定义物理量 ID 与现有预设重复")
                result[q.id] = q
            return result

    def recent(self):
        with _preference_lock:
            return self._load()["recent"][:10]

    def remember(self, preset_id, unit):
        with _preference_lock:
            q = self.presets()[preset_id]
            validate_quantity_unit(q,unit)
            row = dict(preset_id=preset_id,unit=unit)
            data = self._load()
            data["recent"] = [row] + [x for x in data["recent"] if x != row][:9]
            self._save(data)

    def add_custom(self, zh, en, unit):
        if not all(isinstance(v,str) and v.strip() for v in (zh,en,unit)):
            raise ValueError("自定义预设需要中英文名称和单位")
        with _preference_lock:
            data = self._load()
            identity = "custom_" + uuid4().hex
            data["custom"].append(dict(id=identity,zh=zh.strip(),en=en.strip(),units=[unit.strip()],
                                       default_unit=unit.strip(),category="自定义",dimension="custom"))
            self._save(data)
        return identity
