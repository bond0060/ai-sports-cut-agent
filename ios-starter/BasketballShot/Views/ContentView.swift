import SwiftUI

struct ContentView: View {
    @StateObject private var appModel = AppViewModel()
    @State private var selectedVideoURL: URL?
    @State private var showPicker = false
    @State private var isAnalyzing = false

    var body: some View {
        NavigationStack {
            List {
                if let error = appModel.loadError {
                    Section {
                        Text("模型加载失败：\(error)")
                            .foregroundStyle(.red)
                        Text("请确认 best.mlpackage 已加入 Target，且类名为 best。")
                            .font(.caption)
                    }
                }

                Section {
                    if let url = selectedVideoURL {
                        Text(url.lastPathComponent)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Button("选择视频") { showPicker = true }
                    Button("开始分析") { startAnalysis() }
                        .disabled(
                            selectedVideoURL == nil
                                || isAnalyzing
                                || appModel.analyzer == nil
                        )
                }

                if let analyzer = appModel.analyzer {
                    Section("状态") {
                        if isAnalyzing {
                            ProgressView(value: analyzer.progress)
                        }
                        Text(analyzer.status)
                    }

                    Section("统计") {
                        LabeledContent("投篮", value: "\(analyzer.summary.attempts)")
                        LabeledContent("进球", value: "\(analyzer.summary.makes)")
                        LabeledContent(
                            "命中率",
                            value: String(format: "%.1f%%", analyzer.summary.percentage)
                        )
                    }

                    if !analyzer.summary.shots.isEmpty {
                        Section("逐球记录") {
                            ForEach(analyzer.summary.shots) { shot in
                                HStack {
                                    Text("#\(shot.attempt)")
                                    Spacer()
                                    Text(String(format: "%.2fs", shot.timeSeconds))
                                        .foregroundStyle(.secondary)
                                    Text(shot.result.displayName)
                                        .font(.caption.bold())
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(
                                            shot.result == .make
                                                ? Color.green.opacity(0.25)
                                                : Color.red.opacity(0.25)
                                        )
                                        .clipShape(Capsule())
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("篮球投篮检测")
            .sheet(isPresented: $showPicker) {
                VideoPicker(url: $selectedVideoURL)
            }
        }
    }

    private func startAnalysis() {
        guard let url = selectedVideoURL, let analyzer = appModel.analyzer else { return }
        isAnalyzing = true
        Task {
            do {
                try await analyzer.analyze(url: url)
            } catch {
                analyzer.status = "失败：\(error.localizedDescription)"
            }
            isAnalyzing = false
        }
    }
}

#Preview {
    ContentView()
}
