import Foundation
import Glibc

func activeRun(_ root: URL) -> Doc? {
    let path = root.appendingPathComponent("implementations/benchmarks/state/active.json")
    guard let data = try? Data(contentsOf: path), let run = try? parseJSON(data) as? Doc,
          number(run["started_at"], .infinity) <= now(), now() < number(run["deadline"]) else { return nil }
    return run
}
func emit(_ run: Doc, event: String, fields: Doc) {
    guard now() >= number(run["started_at"], .infinity), now() < number(run["deadline"]),
          let path = run["events_path"] as? String else { return }
    var eventFields = fields
    eventFields["schema"] = 1; eventFields["run_id"] = run["run_id"]
    eventFields["ts"] = now(); eventFields["event"] = event
    guard var line = try? jsonData(eventFields) else { return }
    line.append(10)
    let fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, mode_t(0o600))
    guard fd >= 0 else { return }; defer { close(fd) }
    let written = line.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
    if written != line.count { log("benchmark event write failed", warning: true) }
}
final class Metrics {
    private let lock = NSLock()
    private let run: Doc?
    private let taskID: String
    private let module: String
    private let wait: Any
    private let start = DispatchTime.now().uptimeNanoseconds
    private var counters: [String: UInt64] = [:]
    init(root: URL? = nil, taskID: String = "", module: String = "", created: Double? = nil) {
        run = root.flatMap(activeRun); self.taskID = taskID; self.module = module
        wait = created.map { max(0, now() - $0) } as Any? ?? null
        if let run { emit(run, event: "job_start", fields: ["task_id": taskID, "module": module, "queue_wait_seconds": wait]) }
    }
    func count(_ key: String, _ value: UInt64 = 1) {
        guard run != nil else { return }
        lock.lock(); counters[key, default: 0] += value; lock.unlock()
    }
    func finish(_ error: Error?) {
        guard let run else { return }
        lock.lock(); let values = counters; lock.unlock()
        let duration = Double(DispatchTime.now().uptimeNanoseconds - start) / 1e9
        emit(run, event: "job_end", fields: ["task_id": taskID, "module": module,
            "status": error == nil ? "success" : "failed", "error_type": error.map { safeError($0).description } as Any? ?? null,
            "duration_seconds": duration, "queue_wait_seconds": wait, "counters": values])
    }
    func post(channel: String, url: String, sent: Bool) {
        count(sent ? "posts_recorded_sent" : "candidates_rejected")
        if sent, let run, let hash = try? digest(channel.lowercased() + "\0" + url.lowercased()) {
            emit(run, event: "post_record", fields: ["task_id": taskID, "post_key": hash])
        }
    }
    func delivery(_ result: Any) {
        let messages = result as? [Any] ?? [result]
        for item in messages {
            let message = object(item); guard message["message_id"] != nil else { continue }
            count("telegram_messages")
            let kind = ["video", "animation", "photo", "document", "audio"].first { message[$0] != nil } ?? "text_or_other"
            count("telegram_messages_" + kind)
        }
    }
}
