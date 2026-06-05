import CoreGraphics
import Foundation

/// Parses Ultralytics YOLOv8 Core ML output shape [1, 4+nc, 8400].
enum YOLOPostProcessor {
    static let anchorCount = 8400
    static let numClasses = 2
    static let confidenceThreshold: Float = 0.25
    static let iouThreshold: Float = 0.45

    static func decode(
        values: [Float],
        imageSize: CGSize
    ) -> [BoundingBox] {
        let channels = 4 + numClasses
        guard values.count >= channels * anchorCount else { return [] }

        var candidates: [BoundingBox] = []

        for i in 0..<anchorCount {
            let cx = values[0 * anchorCount + i]
            let cy = values[1 * anchorCount + i]
            let w = values[2 * anchorCount + i]
            let h = values[3 * anchorCount + i]

            let ballScore = values[4 * anchorCount + i]
            let hoopScore = values[5 * anchorCount + i]

            let classId: DetectionClass
            let score: Float
            if ballScore >= hoopScore {
                classId = .basketball
                score = ballScore
            } else {
                classId = .hoop
                score = hoopScore
            }

            guard score >= confidenceThreshold else { continue }

            let rect = CGRect(
                x: CGFloat(cx - w / 2) * imageSize.width,
                y: CGFloat(cy - h / 2) * imageSize.height,
                width: CGFloat(w) * imageSize.width,
                height: CGFloat(h) * imageSize.height
            )
            candidates.append(BoundingBox(classId: classId, confidence: score, rect: rect))
        }

        return nonMaxSuppression(candidates)
    }

    private static func nonMaxSuppression(_ boxes: [BoundingBox]) -> [BoundingBox] {
        var result: [BoundingBox] = []
        var byClass: [DetectionClass: [BoundingBox]] = [:]
        for box in boxes {
            byClass[box.classId, default: []].append(box)
        }

        for cls in DetectionClass.allCases {
            var remaining = byClass[cls] ?? []
            remaining.sort { $0.confidence > $1.confidence }
            while let best = remaining.first {
                result.append(best)
                remaining.removeFirst()
                remaining.removeAll { iou(best.rect, $0.rect) > iouThreshold }
            }
        }
        return result
    }

    private static func iou(_ a: CGRect, _ b: CGRect) -> Float {
        let inter = a.intersection(b)
        guard !inter.isNull else { return 0 }
        let interArea = Float(inter.width * inter.height)
        let unionArea = Float(a.width * a.height + b.width * b.height) - interArea
        guard unionArea > 0 else { return 0 }
        return interArea / unionArea
    }
}
