import Foundation

/// Mirrors `swishai_analyzer.py` class map and thresholds.
enum SwishAIConstants {
    static let classNames: [Int: String] = [
        0: "Ball",
        1: "Ball in Basket",
        2: "Player",
        3: "Basket",
        4: "Player Shooting",
    ]

    static let classThresholds: [Int: Float] = [
        0: 0.60,
        1: 0.25,
        2: 0.70,
        3: 0.70,
        4: 0.77,
    ]

    static let shotCooldownSeconds: Double = 1.5
    static let basketCooldownSeconds: Double = 2.0
    static let modelInputSize: CGFloat = 640
}

struct SwishAIDetection {
    let classId: Int
    let confidence: Float
    let rect: CGRect
    let center: CGPoint

    init(classId: Int, confidence: Float, rect: CGRect) {
        self.classId = classId
        self.confidence = confidence
        self.rect = rect
        self.center = CGPoint(x: rect.midX, y: rect.midY)
    }

    var passesThreshold: Bool {
        guard let minConf = SwishAIConstants.classThresholds[classId] else { return false }
        return confidence >= minConf
    }
}
