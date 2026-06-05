import AVFoundation
import Combine
import CoreGraphics
import Foundation

@MainActor
final class VideoAnalyzer: ObservableObject {
    @Published var progress: Double = 0
    @Published var status = ""
    @Published var summary = AnalysisSummary()

    private let detector: CoreMLDetector
    private let frameSkip = 2

    init(detector: CoreMLDetector) {
        self.detector = detector
    }

    func analyze(url: URL) async throws {
        progress = 0
        status = "读取视频…"
        summary = AnalysisSummary()

        let asset = AVURLAsset(url: url)
        guard let track = try await asset.loadTracks(withMediaType: .video).first else {
            throw AnalysisError.noVideoTrack
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

        var tracker = ShotTracker(fps: Double(fps))
        var frameIndex = 0
        var processed = 0

        status = "分析中…"

        while reader.status == .reading {
            guard let sample = output.copyNextSampleBuffer(),
                  let imageBuffer = CMSampleBufferGetImageBuffer(sample) else {
                break
            }

            if frameIndex % frameSkip == 0 {
                let ciImage = CIImage(cvPixelBuffer: imageBuffer)
                let context = CIContext()
                if let cgImage = context.createCGImage(ciImage, from: ciImage.extent) {
                    let bufferSize = CGSize(
                        width: CGFloat(CVPixelBufferGetWidth(imageBuffer)),
                        height: CGFloat(CVPixelBufferGetHeight(imageBuffer))
                    )
                    if let modelBuffer = CoreMLDetector.makeInputBuffer(from: cgImage) {
                        let boxes = try detector.detect(pixelBuffer: modelBuffer)
                        let scaled = boxes.map { scaleBox($0, from: CGSize(width: 640, height: 640), to: bufferSize) }
                        tracker.processFrame(frameIndex: frameIndex, boxes: scaled, fps: Double(fps))
                    }
                }
                processed += 1
            }

            frameIndex += 1
            if frameIndex % 15 == 0 {
                progress = Double(frameIndex) / Double(totalFrames)
                summary = tracker.summary
            }
        }

        progress = 1
        summary = tracker.summary
        status = "完成：\(summary.makes) / \(summary.attempts)"
    }

    private func scaleBox(_ box: BoundingBox, from src: CGSize, to dst: CGSize) -> BoundingBox {
        let sx = dst.width / src.width
        let sy = dst.height / src.height
        let rect = CGRect(
            x: box.rect.origin.x * sx,
            y: box.rect.origin.y * sy,
            width: box.rect.width * sx,
            height: box.rect.height * sy
        )
        return BoundingBox(classId: box.classId, confidence: box.confidence, rect: rect)
    }

    enum AnalysisError: LocalizedError {
        case noVideoTrack

        var errorDescription: String? {
            switch self {
            case .noVideoTrack: return "无法读取视频轨道"
            }
        }
    }
}

/// Simplified shot tracker (v0.1) — mirrors Python up/down + cooldown.
final class ShotTracker {
    private let fps: Double
    private let cooldownFrames: Int
    private var ballHistory: [(center: CGPoint, frame: Int)] = []
    private var hoopRect: CGRect?
    private var up = false
    private var down = false
    private var upFrame = 0
    private var downFrame = 0
    private var lastAttemptFrame = -9999
    private var sequenceFired = false
    private(set) var summary = AnalysisSummary()

    init(fps: Double) {
        self.fps = fps
        self.cooldownFrames = max(Int(fps * AppConstants.shotCooldownSeconds), 1)
    }

    func processFrame(frameIndex: Int, boxes: [BoundingBox], fps: Double) {
        if let hoop = boxes.first(where: { $0.classId == .hoop && $0.confidence >= AppConstants.hoopConfidenceMin }) {
            hoopRect = hoop.rect
        }

        if let ball = boxes.first(where: { $0.classId == .basketball }) {
            let minConf: Float = hoopRect != nil ? AppConstants.ballConfidenceMinInROI : AppConstants.ballConfidenceMinDefault
            if ball.confidence >= minConf {
                ballHistory.append((ball.center, frameIndex))
                if ballHistory.count > 60 {
                    ballHistory.removeFirst(ballHistory.count - 60)
                }
            }
        }

        guard hoopRect != nil, !ballHistory.isEmpty else { return }

        let y = ballHistory.last!.center.y
        let rimY = hoopRect!.midY - hoopRect!.height * 0.1
        let rimBottom = hoopRect!.midY + hoopRect!.height * 0.5

        if !up, y <= rimY {
            up = true
            upFrame = frameIndex
        }
        if up, !down, y > rimBottom {
            down = true
            downFrame = frameIndex
        }

        let sequenceOK = up && down && upFrame < downFrame
        if !sequenceOK { sequenceFired = false }

        if sequenceOK, !sequenceFired, frameIndex - lastAttemptFrame >= cooldownFrames {
            sequenceFired = true
            lastAttemptFrame = frameIndex
            let attempt = summary.attempts + 1
            let made = checkMake()
            let shot = ShotRecord(
                attempt: attempt,
                timeSeconds: Double(frameIndex) / fps,
                frame: frameIndex,
                result: made ? .make : .miss,
                trajectoryCross: made,
                netSwish: false
            )
            summary.attempts = attempt
            if made { summary.makes += 1 }
            summary.shots.append(shot)
            up = false
            down = false
            sequenceFired = false
        }
    }

    private func checkMake() -> Bool {
        guard let hoop = hoopRect, ballHistory.count >= 2 else { return false }
        let rimY = hoop.midY - hoop.height * 0.1
        let rimX1 = hoop.minX + hoop.width * 0.1
        let rimX2 = hoop.maxX - hoop.width * 0.1
        for point in ballHistory {
            if point.center.y >= rimY, point.center.x >= rimX1, point.center.x <= rimX2 {
                return true
            }
        }
        return false
    }
}
