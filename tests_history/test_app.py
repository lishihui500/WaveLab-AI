from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from wavelab.workbench import Workbench

ROOT = Path(__file__).resolve().parents[1]


def find(at, kind, label):
    return next(e for e in getattr(at, kind) if e.label == label)


def click(at, label):
    find(at, "button", label).click().run(timeout=30)
    assert not at.exception
    return at


def loaded(tmp_path):
    at = AppTest.from_file(ROOT / "app.py", default_timeout=30)
    at.session_state["workbench"] = Workbench(tmp_path)
    at.run()
    find(at, "text_area", "含 Domain 表头的数据").input("Domain,u,u\n0,1,2\n1,3,4").run()
    click(at, "导入粘贴文本")
    find(at, "checkbox", "本数据集全部通道加入目标子图").check()
    click(at, "应用通道选择")
    return at


def test_gui_edit_undo_save_reopen(tmp_path):
    at = loaded(tmp_path)
    w = at.session_state["workbench"]
    assert len(w.spec.panels[0].series) == 2
    cid=w.spec.panels[0].series[0].channel_id
    w.set_channel_properties({cid:dict(display_name="电流")});at.run()
    find(at, "text_input", "颜色（留空使用科研配色）").input("#D55E00").run()
    find(at, "selectbox", "线型").select("--").run()
    assert w.spec.datasets[0].channels[0].display_name == "电流"
    click(at, "撤销")
    assert find(at, "selectbox", "线型").value == "-"
    assert w.spec.datasets[0].channels[0].display_name == "电流"
    click(at, "恢复")
    assert w.spec.datasets[0].channels[0].display_name == "电流"
    click(at, "添加子图")
    find(at, "selectbox", "曲线所属子图").select("panel_2").run()
    click(at, "移动曲线")
    assert len(w.spec.panels[1].series) == 1
    find(at, "text_input", "X 范围（显示单位，逗号分隔）").input("0, 0.5").run()
    # Switching s to ms preserves the physical window and updates displayed limits.
    find(at, "selectbox", "显示单位").select("ms").run()
    assert w.spec.time_axis.xlim == (0, 500)
    find(at, "text_input", "Y 范围（逗号分隔）").input("0, 10").run()
    assert w.spec.panels[0].ylim == (0, 10)
    find(at, "number_input", "高度 / in（0 自动）").set_value(6.).run()
    assert w.spec.page.height_in == 6.
    find(at, "selectbox", "坐标轴与标题语言").select("en").run()
    assert w.spec.languages.axes == "en" and w.spec.languages.legend == "zh"
    click(at, "保存工程")
    expected = w.spec.panels
    click(at, "打开所选工程")
    assert w.spec.panels == expected
    # A new Streamlit session, with no original memory or uploads.
    fresh = AppTest.from_file(ROOT / "app.py", default_timeout=30)
    fresh.session_state["workbench"] = Workbench(tmp_path)
    fresh.run()
    click(fresh, "打开所选工程")
    assert fresh.session_state["workbench"].spec.panels == expected
    find(fresh, "checkbox", "显示曲线").uncheck().run()
    assert not fresh.session_state["workbench"].spec.panels[0].series[0].visible
    click(fresh, "删除所选曲线")
    assert not fresh.session_state["workbench"].spec.panels[0].series


def test_gui_invalid_input_keeps_previous_state(tmp_path):
    at = loaded(tmp_path)
    w = at.session_state["workbench"]
    original = w.spec
    find(at, "text_input", "Y 范围（逗号分隔）").input("10, 0").run()
    assert at.error and w.spec == original


def test_gui_edit_does_not_reparse_and_events(tmp_path, monkeypatch):
    at = loaded(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("A visual edit reparsed source data")
    monkeypatch.setattr("wavelab.workbench.parse_file", forbidden)
    field = find(at, "number_input", "事件绝对时刻 / s")
    field.set_value(1.2)
    find(at, "text_input", "事件名称 · English").input("Fault")
    click(at, "保存事件")
    w = at.session_state["workbench"]
    assert w.spec.events[0].time_s == 1.2
    find(at, "selectbox", "编辑事件").select(0).run()
    find(at, "text_input", "事件颜色").input("red")
    click(at, "保存事件")
    assert w.spec.events[0].color == "red"
    find(at, "selectbox", "编辑事件").select(0).run()
    click(at, "删除事件")
    assert w.spec.events == ()


@pytest.mark.parametrize("path", sorted((ROOT / "test" / "fixtures").glob("*.txt")), ids=lambda p: p.name)
def test_gui_real_file_import(tmp_path, path):
    at = AppTest.from_file(ROOT / "app.py", default_timeout=30)
    at.session_state["workbench"] = Workbench(tmp_path)
    at.run()
    find(at, "text_input", "本地数据文件路径").input(str(path)).run()
    click(at, "导入本地文件")
    w = at.session_state["workbench"]
    assert len(w.spec.datasets) == 1
    assert len(w.spec.datasets[0].channels) > 0
    find(at, "checkbox", "本数据集全部通道加入目标子图").check()
    click(at, "应用通道选择")
    assert len(w.spec.panels[0].series) == len(w.spec.datasets[0].channels)
