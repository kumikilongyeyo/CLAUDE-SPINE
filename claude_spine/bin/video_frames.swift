// video_frames <video> <out_dir> <fps> <max_edge> <limit>
// Samples a video at `fps` (whole clip, at most `limit` frames) with AVFoundation and writes f_000001.png ...
// at most `max_edge` px on the long side, alpha kept (ProRes 4444 / HEVC with alpha). Prints one JSON line:
// {"duration": seconds, "fps": sampling fps, "count": frames, "width": w, "height": h}.
// ae_fx_memory uses it on macOS when ffmpeg is not installed.
import AVFoundation
import Foundation
import ImageIO
import UniformTypeIdentifiers

let a = CommandLine.arguments
guard a.count == 6, let fps0 = Double(a[3]), let edge = Double(a[4]), let limit = Int(a[5]) else {
    FileHandle.standardError.write("usage: video_frames <video> <out_dir> <fps> <max_edge> <limit>\n".data(using: .utf8)!)
    exit(2)
}
let asset = AVURLAsset(url: URL(fileURLWithPath: a[1]))
let sem = DispatchSemaphore(value: 0)
var seconds = 0.0
Task {
    if let d = try? await asset.load(.duration) { seconds = d.seconds }
    sem.signal()
}
sem.wait()
guard seconds > 0 else {
    FileHandle.standardError.write("no readable video track in \(a[1])\n".data(using: .utf8)!)
    exit(1)
}
let fps = max(0.25, min(fps0, Double(limit) / seconds))
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = .zero
gen.maximumSize = CGSize(width: edge, height: edge)
let out = URL(fileURLWithPath: a[2], isDirectory: true)
try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
var count = 0, w = 0, h = 0
while count < limit {
    let t = Double(count) / fps
    if t > seconds - 0.5 / fps && count > 0 { break }
    guard let img = try? gen.copyCGImage(at: CMTime(seconds: t, preferredTimescale: 60000), actualTime: nil) else { break }
    w = img.width; h = img.height
    let url = out.appendingPathComponent(String(format: "f_%06d.png", count + 1))
    guard let dst = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else { exit(1) }
    CGImageDestinationAddImage(dst, img, nil)
    CGImageDestinationFinalize(dst)
    count += 1
}
print("{\"duration\": \(seconds), \"fps\": \(fps), \"count\": \(count), \"width\": \(w), \"height\": \(h)}")
