"""Export initial-state illustrations only; no measured task is executed."""
from pathlib import Path
from wavelab.workbench import Workbench
from wavelab.render.engine import render_figure,export_figure
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/stage_03F'
for task in ['F01','F02','F03']:
    w=Workbench(OUT/'baseline_preview_workspace'/task);w.open_project(OUT/'baselines'/task/'project.json')
    for language in ['zh','en']:
        view=w.spec.model_copy(update={'languages':w.spec.languages.model_copy(update={'axes':language,'legend':language})})
        r=render_figure(view,w.datasets);export_figure(r,OUT/'figures'/f'{task}_initial_{language}.png');r.figure.clear()
print('Six synthetic baseline PNGs exported; source and benchmark tasks untouched.')
