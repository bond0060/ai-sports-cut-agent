import AVFoundation
import Combine
import CoreGraphics
import Foundation

/// SwishAI video analysis skeleton — wire up your Core ML model in `detectSwishAI`.
@MainActor
final class SwishAIVideoAnalyzer: ObservableObject {
    @Published var progress: Double = 0
    @Published var status = ""
    @Published var makes = 0
    @Published var attempts = 0
    @Published var shots: [ShotRecord] = []

    private let frameSkip = 1

    func analyze(url: URL, detectSwishAI: (CVPixelBuffer) throws -> [SwishAIDetection]) async throws {
        progress = 0
        status = "读取视频…"
        makes = 0
        attempts = 0
        shots = []

        let asset = AVURLAsset(url: url)
        guard let track = try await asset.loadTracks(withMediaType: .video).first else {
            throw SwishAIAnalysisError.noVideoTrack
        }

        let duration = try await asset.load(.duration)
        let fps = try await track.load(.nominalFrameRate)
        let totalFrames = max(Int(CMTimeGetSeconds(duration) * Double(fps)), 1)

        let reader = try AVAssetReader(asset: asset)
        let outputSettings: [String: Any] = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        ]
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: outputSettings)
        reader.add(output)
        reader.startReading()

        var tracker = SwishAITracker(fps: Double(fps))
        var frameIndex = 0
        status = "SwishAI 分析中…"

        while reader.status == .reading {
            guard let sample = output.copyNextSampleBuffer(),
                  let imageBuffer = CMSampleBufferGetImageBuffer(sample) else {
                break
            }

            if frameIndex % frameSkip == 0,
               let modelBuffer = CoreMLDetector.makeInputBuffer(from: pixelBufferAsCGImage(imageBuffer)) {
                let detections = try detectSwishAI(modelBuffer)
                let bufferSize = CGSize(
                    width: CGFloat(CVPixelBufferGetWidth(imageBuffer)),
                    height: CGFloat(CVPixelBufferGetHeight(imageBuffer))
                )
                let scaled = detections.map { scaleDetection($0, to: bufferSize) }
                tracker.processFrame(frameIndex: frameIndex, detections: scaled)
            }

            frameIndex += 1
            if frameIndex % 15 == 0 {
                progress = Double(frameIndex) / Double(totalFrames)
                makes = tracker.makes
                attempts = tracker.attempts
                shots = tracker.shots
            }
        }

        progress = 1
        makes = tracker.makes
        attempts = tracker.attempts
        shots = tracker.shots
        status = "完成：\(makes) / \(attempts)"
    }

    private func pixelBufferAsCGImage(_ buffer: CVPixelBuffer) -> CGImage {
        let ci = CIImage(cvPixelBuffer: buffer)
        let ctx = CIContext()
        return ctx.createCGImage(ci, from: ci.extent)!
    }

    private func scaleDetection(_ det: SwishAIDetection, to dst: CGSize) -> SwishAIDetection {
        let src = CGSize(width: SwishAIConstants.modelInputSize, height: SwishAIConstants.modelInputSize)
        let sx = dst.width / src.width
        let sy = dst.height / src.height
        let rect = CGRect(
            x: det.rect.origin.x * sx,
            y: det.rect.origin.y * sy,
            width: det.rect.width * sx,
            height: det.rect.height * sy
        )
        return SwishAIDetection(classId: det.classId, confidence: det.confidence, rect: rect)
    }

    enum SwishAIAnalysisError: LocalizedError {
        case noVideoTrack

        var errorDescription: String? {
            switch self {
            case .noVideoTrack: return "无法读取视频轨道"
            }
        }
    }
}
