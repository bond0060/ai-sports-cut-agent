import CoreML
import CoreVideo
import UIKit
import Vision

final class CoreMLDetector {
    private let mlModel: MLModel
    private let inputSize = CGSize(width: 640, height: 640)

    init() throws {
        let config = MLModelConfiguration()
        config.computeUnits = .all
        mlModel = try best(configuration: config).model
    }

    func detect(pixelBuffer: CVPixelBuffer) throws -> [BoundingBox] {
        let input = try MLDictionaryFeatureProvider(
            dictionary: ["image": MLFeatureValue(pixelBuffer: pixelBuffer)]
        )
        let output = try mlModel.prediction(from: input)

        guard let multi = output.featureValue(for: "var_910")?.multiArrayValue else {
            if let named = output.featureNames.first,
               let multi = output.featureValue(for: named)?.multiArrayValue {
                return parse(multi: multi)
            }
            return []
        }
        return parse(multi: multi)
    }

    private func parse(multi: MLMultiArray) -> [BoundingBox] {
        let count = multi.count
        var floats = [Float](repeating: 0, count: count)
        for i in 0..<count {
            floats[i] = multi[i].floatValue
        }
        return YOLOPostProcessor.decode(values: floats, imageSize: inputSize)
    }

    /// Resize frame to 640×640 BGRA pixel buffer for model input.
    static func makeInputBuffer(from image: CGImage) -> CVPixelBuffer? {
        let width = 640
        let height = 640
        var buffer: CVPixelBuffer?
        let attrs = [
            kCVPixelBufferCGImageCompatibilityKey: true,
            kCVPixelBufferCGBitmapContextCompatibilityKey: true,
        ] as CFDictionary
        CVPixelBufferCreate(
            kCFAllocatorDefault,
            width,
            height,
            kCVPixelFormatType_32BGRA,
            attrs,
            &buffer
        )
        guard let pixelBuffer = buffer else { return nil }

        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, []) }

        guard let context = CGContext(
            data: CVPixelBufferGetBaseAddress(pixelBuffer),
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: CVPixelBufferGetBytesPerRow(pixelBuffer),
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue
        ) else {
            return nil
        }

        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return pixelBuffer
    }
}
