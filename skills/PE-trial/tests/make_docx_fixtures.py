#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 DOCX 测试 fixtures（纯标准库手写最小 OOXML）。

- good_a4.docx：A4 11906x16838 twips、四边 1417 twips（2.5cm）、
  3 列表格总宽 7200 twips、styles.xml 声明 eastAsia 中文字体。
- bad_table11.docx：Letter 尺寸 12240x15840、边距 1440、
  11 列表格总宽 9900 twips（>16cm 且 >=11 列）、无 eastAsia 声明。

运行：python3 tests/make_docx_fixtures.py [输出目录，默认 tests/fixtures/docx]
"""
import os
import sys
import zipfile

CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

STYLES_WITH_CJK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Helvetica" w:hAnsi="Helvetica" w:eastAsia="Songti SC"/>
<w:sz w:val="21"/>
</w:rPr></w:rPrDefault></w:docDefaults>
</w:styles>"""

STYLES_NO_CJK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Helvetica" w:hAnsi="Helvetica"/>
<w:sz w:val="21"/>
</w:rPr></w:rPrDefault></w:docDefaults>
</w:styles>"""


def doc_xml(pg_w, pg_h, margin, col_widths, col_count):
    grid = "".join('<w:gridCol w:w="%d"/>' % w for w in
                   (col_widths * col_count)[:col_count])
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/></w:tblPr>
<w:tblGrid>%s</w:tblGrid></w:tbl>
<w:p/>
<w:sectPr>
<w:pgSz w:w="%d" w:h="%d"/>
<w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d"
 w:header="708" w:footer="708" w:gutter="0"/>
</w:sectPr>
</w:body>
</w:document>""" % (sum((col_widths * col_count)[:col_count]), grid,
                    pg_w, pg_h, margin, margin, margin, margin)


def write_docx(path, document, styles):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/styles.xml", styles)


def main(outdir=None):
    base = outdir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "fixtures", "docx")
    os.makedirs(base, exist_ok=True)
    good = os.path.join(base, "good_a4.docx")
    bad = os.path.join(base, "bad_table11.docx")
    write_docx(good, doc_xml(11906, 16838, 1417, [2400], 3), STYLES_WITH_CJK)
    write_docx(bad, doc_xml(12240, 15840, 1440, [900], 11), STYLES_NO_CJK)
    print("wrote:", good)
    print("wrote:", bad)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
