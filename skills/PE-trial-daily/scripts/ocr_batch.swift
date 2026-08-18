import Foundation
import Vision
import PDFKit
import AppKit

// 用法: swift ocr_batch.swift <pdf> <startPage> <endPage>
// 输出每行: "PAGE\t<页码>\t<识别文本>\t<x>\t<y>\t<w>\t<h>"
// 其中 x/y/w/h 为归一化坐标（0-1，Vision 原点在左下），供精确裁图定位 caption。
let args = CommandLine.arguments
guard args.count >= 4 else {
    print("USAGE: ocr_batch <pdf> <startPage> <endPage>")
    exit(1)
}
let pdfPath = args[1]
let start = Int(args[2]) ?? 0
let end = Int(args[3]) ?? 0

guard let doc = PDFDocument(url: URL(fileURLWithPath: pdfPath)) else {
    print("ERR: cannot open pdf")
    exit(1)
}

let colorSpace = CGColorSpaceCreateDeviceRGB()
let scale: CGFloat = 3.0

func ocrPage(_ page: PDFPage) -> [(String, CGFloat, CGFloat, CGFloat, CGFloat)] {
    let bounds = page.bounds(for: .mediaBox)
    let width = Int(bounds.width * scale)
    let height = Int(bounds.height * scale)
    guard let ctx = CGContext(data: nil, width: width, height: height,
                              bitsPerComponent: 8, bytesPerRow: 0,
                              space: colorSpace,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return []
    }
    ctx.setFillColor(CGColor(gray: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    guard let cgImage = ctx.makeImage() else { return [] }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try? handler.perform([request])
    var out: [(String, CGFloat, CGFloat, CGFloat, CGFloat)] = []
    for obs in request.results ?? [] {
        if let cand = obs.topCandidates(1).first {
            let bb = obs.boundingBox
            // Vision 归一化坐标原点在左下；转成图像坐标（左上原点）便于裁图
            let x = bb.origin.x
            let yTop = 1.0 - bb.origin.y - bb.size.height
            out.append((cand.string, x, yTop, bb.size.width, bb.size.height))
        }
    }
    return out
}

for p in start..<min(end, doc.pageCount) {
    guard let page = doc.page(at: p) else { continue }
    let lines = ocrPage(page)
    for (text, x, y, w, h) in lines {
        let flat = text.replacingOccurrences(of: "\n", with: "␊")
        print(String(format: "PAGE\t%d\t%@\t%.5f\t%.5f\t%.5f\t%.5f", p, flat, x, y, w, h))
    }
}
