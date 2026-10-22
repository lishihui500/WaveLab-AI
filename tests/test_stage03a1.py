from pathlib import Path
import json

import pytest

from test_app import loaded, find, click
from test_workbench import setup
from wavelab.render.engine import render_figure


def edit(at, kind, label, value):
    widget = find(at, kind, label)
    if kind == "selectbox":
        widget.select(value)
    elif kind == "number_input":
        widget.set_value(value)
    elif kind == "checkbox":
        widget.set_value(value)
    else:
        widget.input(value)
    at.run(timeout=30)
    assert not at.exception


def test_auto_edits_twenty_roundtrip(tmp_path, monkeypatch):
    at = loaded(tmp_path)
    w = at.session_state['workbench']
    def forbidden(*args, **kwargs):
        raise AssertionError('Edit must not reparse data')
    with monkeypatch.context() as m:
        m.setattr('wavelab.workbench.parse_file', forbidden)
        operations = [
            ('text_input','子图标题 · 中文','暂态'),
            ('text_input','子图标题 · English','Transient'),
            ('selectbox','坐标轴与标题语言','en'),
            ('text_input','X 范围（显示单位，逗号分隔）','0, 1'),
            ('text_input','Y 范围（逗号分隔）','0, 8'),
            ('text_input','颜色（留空使用科研配色）','#D55E00'),
            ('selectbox','线型','--'),
            ('number_input','线宽 / pt',1.2),
            ('checkbox','显示曲线',False),
            ('checkbox','显示曲线',True),
            ('selectbox','图例位置','upper right'),
            ('number_input','图例列数（0 自动）',2),
            ('selectbox','整体预设','IEEE 英文单栏'),
            ('selectbox','线型',':'),
            ('selectbox','图例语言','en'),
            ('selectbox','图例语言','zh'),
            ('selectbox','坐标轴与标题语言','zh'),
            ('selectbox','坐标轴与标题语言','en'),
        ]
        for op in operations:
            previous = w.revision
            edit(at, *op)
            assert w.revision == previous + 1
        assert w.spec.languages.axes == 'en' and w.spec.languages.legend == 'zh'
        assert w.spec.time_axis.xlim == (0, 1)
        assert w.spec.panels[0].ylim == (0, 8)
        assert w.spec.panels[0].series[0].color == '#D55E00'
        rendered = render_figure(w.spec, w.datasets)
        assert rendered.figure.axes[0].get_xlabel() == 'Time (s)'
        assert rendered.figure.axes[0].get_ylabel() == 'Confirm quantity/unit'
        rendered.figure.clear()
    before = w.spec
    click(at, '保存工程')
    assert w.save_status == '已保存'
    click(at, '打开所选工程')
    assert w.spec.panels == before.panels
    assert w.spec.time_axis == before.time_axis
    assert w.spec.languages == before.languages
    assert w.spec.legend == before.legend


def test_auto_invalid_and_save_failure_preserve_state(tmp_path, monkeypatch):
    at = loaded(tmp_path)
    w = at.session_state['workbench']
    click(at, '保存工程')
    path = w.project_path
    original_file = path.read_bytes()
    before = w.spec
    edit(at, 'text_input', 'Y 范围（逗号分隔）', '8, 1')
    assert at.error and w.spec == before
    edit(at, 'text_input', 'Y 范围（逗号分隔）', '0, 8')
    valid = w.spec
    def failure(*args):
        raise PermissionError('simulated Windows file lock')
    with monkeypatch.context() as m:
        m.setattr('wavelab.workbench.os.replace', failure)
        click(at, '保存工程')
    assert w.spec == valid and w.save_status == '保存失败'
    assert path.read_bytes() == original_file
    assert not list(path.parent.glob('*.tmp'))
    assert 'file lock' in (w.root / 'save_errors.log').read_text(encoding='utf-8')
    click(at, '保存工程')
    assert w.save_status == '已保存'


def test_atomic_saved_document_all_fields(tmp_path):
    w, identity, ids = setup(tmp_path)
    w.map_channels(identity, 'u', 'numbered', 'User confirmed', 'kV')
    w.update(['events'], [dict(time_s=.001, label='事件', label_i18n=dict(zh='故障', en='Fault'), confirmation_source='User')])
    expected = w.spec
    path = w.save_project('中文工程')
    json.loads(path.read_text(encoding='utf-8'))
    w.open_project(path)
    assert w.spec.panels == expected.panels and w.spec.events == expected.events
    assert w.spec.datasets[0].channels == expected.datasets[0].channels


def test_x_label_fallback_visible(tmp_path):
    w, _, _ = setup(tmp_path)
    w.update(['time_axis','label'], '自定义时间')
    w.set_languages('zh','en')
    result = render_figure(w.spec,w.datasets)
    assert result.axes['panel_1'].get_xlabel()=='Time (s)'
    assert w.spec.time_axis.label=='自定义时间'
    assert not any('自定义时间' in warning for warning in result.warnings)
    result.figure.clear()


def test_mixed_legend_font_survives_preset(tmp_path):
    w, _, _ = setup(tmp_path)
    w.set_languages('zh', 'en')
    w.preset('en', 'ieee_single_column', preserve_languages=True)
    assert w.spec.languages.legend == 'zh' and w.spec.languages.axes == 'en'
    assert w.spec.legend.font_family == 'SimSun'
    w.update(['legend', 'font_family'], None)
    result = render_figure(w.spec, w.datasets)
    from matplotlib import font_manager
    if 'SimSun' in {f.name for f in font_manager.fontManager.ttflist}:
        assert all(t.get_fontfamily()[0] == 'SimSun' for a in result.figure.axes if a.get_legend() for t in a.get_legend().get_texts())
    result.figure.clear()


def test_preview_chinese_glyphs_have_visible_pixels(tmp_path):
    from io import BytesIO
    import numpy as np
    from PIL import Image
    from matplotlib import font_manager
    from wavelab.app_preview import preview_png, PREVIEW_DPI
    if 'SimSun' not in {f.name for f in font_manager.fontManager.ttflist}:
        pytest.skip('Windows SimSun raster regression requires installed font')
    w, _, _ = setup(tmp_path)
    w.set_languages('zh', 'en')
    w.assign_channels('panel_1', [w.spec.panels[0].series[0].channel_id])
    w.set_channel_properties({w.spec.panels[0].series[0].channel_id:dict(display_name='相上桥臂')})
    result = render_figure(w.spec, w.datasets)
    text = next(a.get_legend().get_texts()[0] for a in result.figure.axes if a.get_legend())
    box = text.get_window_extent(result.figure.canvas.get_renderer())
    scale = PREVIEW_DPI / result.figure.dpi
    png, notes = preview_png(w.spec, w.datasets)
    pixels = np.asarray(Image.open(BytesIO(png)).convert('RGB'))
    h = pixels.shape[0]
    crop = pixels[max(0,h-int(box.y1*scale)-2):h-int(box.y0*scale)+2,
                  max(0,int(box.x0*scale)-2):int(box.x1*scale)+2]
    assert np.count_nonzero(np.min(crop,axis=2) < 200) > 100
    result.figure.clear()


def test_minimum_font_and_low_dpi_png(tmp_path):
    from PIL import Image
    from wavelab.render.engine import export_figure
    at = loaded(tmp_path)
    edit(at, 'number_input', '基础字号 / pt', 6.)
    assert find(at,'number_input','图例字号 / pt').value >= 6
    w = at.session_state['workbench']
    w.update(['page','dpi'],72)
    result = render_figure(w.spec,w.datasets)
    path = export_figure(result,tmp_path/'low.png')
    with Image.open(path) as image:
        assert image.width == int(w.spec.page.width * 72)
        assert abs(image.info['dpi'][0] - 72) < .1
    result.figure.clear()
