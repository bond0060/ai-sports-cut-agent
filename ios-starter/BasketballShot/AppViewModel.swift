import Combine
import Foundation

@MainActor
final class AppViewModel: ObservableObject {
    @Published var analyzer: VideoAnalyzer?
    @Published var loadError: String?

    init() {
        do {
            let detector = try CoreMLDetector()
            analyzer = VideoAnalyzer(detector: detector)
            loadError = nil
        } catch {
            analyzer = nil
            loadError = error.localizedDescription
        }
    }
}
