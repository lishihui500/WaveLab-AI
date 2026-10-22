"""Validated source metadata patches shared by GUI and Action Executor."""
from wavelab.domain.models import ConfirmedQuantity


def patch_channels(payload, edits, presets, confirmation_source):
    channels = {c['channel_id']: c for m in payload['datasets'] for c in m['channels']}
    for cid, values in edits.items():
        if cid not in channels:
            raise ValueError(f'不存在的通道: {cid}')
        if not set(values) <= {'display_name', 'quantity_name', 'unit'}:
            raise ValueError('仅允许修改图例名称、物理量和源单位')
        c = channels[cid]
        if 'display_name' in values:
            name = values['display_name'].strip()
            if not name:
                raise ValueError('图例名称不能为空')
            c['display_name'] = name
        unit = values.get('unit', c['unit'])
        unit = unit.strip() or None if isinstance(unit, str) else unit
        old = c['quantity']
        name = values.get('quantity_name', old['zh'] if old else '').strip()
        if name:
            same = old and name in (old['zh'], old['en'], old.get('preset_id'))
            # A historical custom name may equal a built-in Chinese name.
            # Editing its legend/unit must not replace its bilingual meaning.
            preset = presets.get(old.get('preset_id')) if same else next(
                (p for p in presets.values() if name in (p.id, p.zh, p.en)), None)
            if preset and preset.id == 'switch_state' and unit:
                raise ValueError('开关状态应选择“无单位”，不改变原始采样值')
            if preset and unit:
                from wavelab.quantity_presets import validate_quantity_unit
                try:
                    validate_quantity_unit(preset, unit)
                except ValueError as exc:
                    raise ValueError(f'{exc}；推荐选择 {preset.default_unit}。请确认数据实际单位；修改单位标签不会换算采样值。') from exc
            c['quantity'] = ConfirmedQuantity(
                preset_id=preset.id if preset else (old.get('preset_id') if same else None),
                zh=preset.zh if preset else (old['zh'] if same else name),
                en=preset.en if preset else (old['en'] if same else name),
                unit=unit, confirmation_source=confirmation_source).model_dump(mode='json')
        else:
            c['quantity'] = None
        c['unit'] = unit
    return payload
