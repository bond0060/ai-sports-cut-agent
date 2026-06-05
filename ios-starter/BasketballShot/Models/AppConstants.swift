import Foundation
import CoreGraphics

/// 与 Python `analyzer.py` / `utils.py` 对齐的常量
enum AppConstants {
    static let classNames = ["Basketball", "Basketball Hoop"]
    static let hoopConfidenceMin: Float = 0.5
    static let ballConfidenceMinDefault: Float = 0.3
    static let ballConfidenceMinInROI: Float = 0.15

    static let shotCooldownSeconds: Double = 3.0
    static let shootingTimeoutSeconds: Double = 4.0
    static let clipBeforeSeconds: Double = 3.0
    static let clipAfterSeconds: Double = 3.0

    static let modelInputSize: CGFloat = 640
}

enum DetectionClass: Int, CaseIterable {
    case basketball = 0
    case hoop = 1
}

struct BoundingBox {
    let classId: DetectionClass
    let confidence: Float
    let rect: CGRect
    let center: CGPoint

    init(classId: DetectionClass, confidence: Float, rect: CGRect) {
        self.classId = classId
        self.confidence = confidence
        self.rect = rect
        self.center = CGPoint(x: rect.midX, y: rect.midY)
    }
}
