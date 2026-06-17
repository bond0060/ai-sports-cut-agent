import CoreGraphics
import Foundation

/// Port of `swishai_analyzer._GameStats` — shot/basket cooldown scoring.
final class SwishAITracker {
    private let fps: Double
    private let shotCooldownFrames: Int
    private let basketCooldownFrames: Int

    private var lastShotFrame = Int.min / 2
    private var lastBasketFrame = Int.min / 2
    private(set) var shotsAttempted = 0
    private(set) var basketsMade = 0
    private(set) var shots: [ShotRecord] = []

    init(fps: Double) {
        self.fps = fps
        self.shotCooldownFrames = max(Int(fps * SwishAIConstants.shotCooldownSeconds), 1)
        self.basketCooldownFrames = max(Int(fps * SwishAIConstants.basketCooldownSeconds), 1)
        self.lastShotFrame = -shotCooldownFrames
        self.lastBasketFrame = -basketCooldownFrames
    }

    var makes: Int { basketsMade }
    var attempts: Int { shotsAttempted }
    var misses: Int { max(0, shotsAttempted - basketsMade) }

    func processFrame(frameIndex: Int, detections: [SwishAIDetection]) {
        for det in detections where det.passesThreshold {
            switch det.classId {
            case 4:
                registerShot(frameIndex: frameIndex)
            case 1:
                registerBasket(frameIndex: frameIndex)
            default:
                break
            }
        }
    }

    private func registerShot(frameIndex: Int) {
        guard frameIndex - lastShotFrame >= shotCooldownFrames else { return }
        shotsAttempted += 1
        lastShotFrame = frameIndex
    }

    private func registerBasket(frameIndex: Int) {
        guard frameIndex - lastBasketFrame >= basketCooldownFrames else { return }
        if frameIndex - lastShotFrame > shotCooldownFrames * 2 {
            shotsAttempted += 1
            lastShotFrame = frameIndex
        }
        basketsMade += 1
        lastBasketFrame = frameIndex
        let record = ShotRecord(
            attempt: basketsMade,
            timeSeconds: Double(frameIndex) / fps,
            frame: frameIndex,
            result: .make,
            trajectoryCross: true,
            netSwish: true
        )
        shots.append(record)
    }
}
