import Foundation

enum ShotResult: String, Codable {
    case make = "Make"
    case miss = "Miss"

    var displayName: String {
        switch self {
        case .make: return "进球"
        case .miss: return "未进"
        }
    }
}

struct ShotRecord: Identifiable, Codable {
    let id: UUID
    let attempt: Int
    let timeSeconds: Double
    let frame: Int
    let result: ShotResult
    var trajectoryCross: Bool
    var netSwish: Bool

    init(
        attempt: Int,
        timeSeconds: Double,
        frame: Int,
        result: ShotResult,
        trajectoryCross: Bool = false,
        netSwish: Bool = false
    ) {
        self.id = UUID()
        self.attempt = attempt
        self.timeSeconds = timeSeconds
        self.frame = frame
        self.result = result
        self.trajectoryCross = trajectoryCross
        self.netSwish = netSwish
    }
}

struct AnalysisSummary {
    var makes: Int = 0
    var attempts: Int = 0
    var shots: [ShotRecord] = []

    var misses: Int { attempts - makes }
    var percentage: Double {
        guard attempts > 0 else { return 0 }
        return Double(makes) / Double(attempts) * 100
    }
}
