"""Local PNG visual sheet and PDF geometry/text checks; no external uploads."""
from pathlib import Path
import json
from PIL import Image, ImageDraw
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"reports"/"stage_03B"


def main():
    paths=sorted((OUT/"mock").glob("case_*.png"))
    assert len(paths)==8
    sheet=Image.new("RGB",(1600,1800),"white")
    draw=ImageDraw.Draw(sheet)
    for i,path in enumerate(paths):
        picture=Image.open(path).convert("RGB")
        picture.thumbnail((780,410))
        x,y=(i%2)*800,(i//2)*450
        draw.text((x+12,y+8),path.stem,fill="black")
        sheet.paste(picture,(x+(800-picture.width)//2,y+30))
    sheet.save(OUT/"contact_sheet.png")
    checked=[]
    for path in sorted((OUT/"mock").glob("case_*.pdf")):
        reader=PdfReader(path)
        assert len(reader.pages)==1
        page=reader.pages[0]
        width=float(page.mediabox.width)/72
        assert abs(width-(3.5 if path.name.startswith("case_4") else 7.16))<0.005
        text=page.extract_text()
        assert text.strip()
        checked.append({"file":path.name,"pages":1,"width_in":width,"text":text})
    assert len(checked)==8
    (OUT/"pdf_checks.json").write_text(json.dumps(checked,ensure_ascii=False,indent=2),encoding="utf-8")
    print("8 PDF page/width/text checks; 8 PNGs in contact_sheet.png")


if __name__=="__main__":
    main()
