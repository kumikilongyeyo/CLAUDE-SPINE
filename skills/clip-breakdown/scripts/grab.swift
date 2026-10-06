// Frame grabber for macOS (no ffmpeg needed): AVAssetImageGenerator, exact times, JPEG out.
//   grab info <video>
//   grab frames <video> <outdir> <n> [t0] [t1] [maxsize] [uniform]
// frames: n frames between t0 and t1 (default the whole clip). Default spacing samples the middle of n equal slices;
// "uniform" puts the first frame on t0 and the last on t1 (for motion curves and spacing charts).
// File names: f0000_12.345s.jpg (index, time in seconds).
import AVFoundation
import AppKit

let a = CommandLine.arguments
func fail(_ m: String) -> Never { FileHandle.standardError.write((m + "\n").data(using: .utf8)!); exit(1) }
if a.count < 3 { fail("usage: grab info <video> | grab frames <video> <outdir> <n> [t0] [t1] [maxsize] [uniform]") }
let asset = AVURLAsset(url: URL(fileURLWithPath: a[2]))
let dur = CMTimeGetSeconds(asset.duration)
guard let tr = asset.tracks(withMediaType: .video).first else { fail("no video track in " + a[2]) }
let sz = tr.naturalSize.applying(tr.preferredTransform)
if a[1] == "info" {
  print("{\"duration\": \(dur), \"width\": \(abs(sz.width)), \"height\": \(abs(sz.height)), \"fps\": \(tr.nominalFrameRate)}")
  exit(0)
}
if a.count < 5 { fail("frames needs <video> <outdir> <n>") }
let out = a[3], n = max(1, Int(a[4])!)
let t0 = a.count > 5 ? Double(a[5])! : 0, t1 = a.count > 6 ? min(Double(a[6])!, dur) : dur
let maxSize = a.count > 7 ? Double(a[7])! : 960
let uniform = a.count > 8 && a[8] == "uniform"
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)
let g = AVAssetImageGenerator(asset: asset)
g.appliesPreferredTrackTransform = true
g.requestedTimeToleranceBefore = .zero; g.requestedTimeToleranceAfter = .zero
g.maximumSize = CGSize(width: maxSize, height: maxSize)
for i in 0..<n {
  let t = uniform ? (n == 1 ? t0 : t0 + (t1 - t0) * Double(i) / Double(n - 1)) : t0 + (t1 - t0) * (Double(i) + 0.5) / Double(n)
  guard let cg = try? g.copyCGImage(at: CMTime(seconds: min(t, dur - 0.001), preferredTimescale: 600), actualTime: nil) else { continue }
  let rep = NSBitmapImageRep(cgImage: cg)
  let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.88])!
  try! data.write(to: URL(fileURLWithPath: String(format: "%@/f%04d_%.3fs.jpg", out, i, t)))
}
