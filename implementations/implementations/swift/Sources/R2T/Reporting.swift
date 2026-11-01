import Foundation

// The Cocoa SDK does not provide the server-side Linux transport. Send the
// documented envelope format from a bounded, dedicated transport queue. Only
// safe native categories and module names enter events; URLs/errors from HTTP
// libraries are never serialized. Reporting requests are outside job counters.
final class Reporter {
    private let queue = OperationQueue()
    private let dsn: String?
    private let endpoint: String?
    init(config: Config) throws {
        queue.maxConcurrentOperationCount = 1
        let raw = text(config.values["sentry"])
        if raw.isEmpty { dsn = nil; endpoint = nil; return }
        guard let url = URLComponents(string: raw), let scheme = url.scheme,
              ["http", "https"].contains(scheme), let host = url.host,
              url.user != nil else { throw R2TError.config }
        let parts = url.path.split(separator: "/").map(String.init)
        guard let project = parts.last, !project.isEmpty else { throw R2TError.config }
        var target = URLComponents(); target.scheme = scheme; target.host = host; target.port = url.port
        target.path = "/" + (parts.dropLast() + ["api", project, "envelope", ""]).joined(separator: "/")
        guard let endpoint = target.string else { throw R2TError.config }
        self.dsn = raw; self.endpoint = endpoint
    }
    func capture(_ error: Error, module: String) {
        guard let dsn, let endpoint, queue.operationCount < 30 else { return }
        let category = safeError(error).description
        let id = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        queue.addOperation {
            do {
                let event: Doc = ["event_id": id, "timestamp": now(), "platform": "other", "level": "error",
                    "logger": "r2t-swift", "release": BuildInfo.version,
                    "exception": ["values": [["type": category, "value": category]]], "extra": ["submodule": module]]
                let body = try jsonData(event)
                var envelope = try jsonData(["event_id": id, "dsn": dsn]); envelope.append(10)
                envelope.append(try jsonData(["type": "event", "length": body.count])); envelope.append(10)
                envelope.append(body); envelope.append(10)
                let http = try HTTP(metrics: Metrics())
                _ = try http.request("POST", endpoint, headers: ["Content-Type": "application/x-sentry-envelope"], body: envelope)
            } catch { log("Sentry reporting failed: \(safeError(error))", warning: true) }
        }
    }
    func close() {
        let deadline = DispatchTime.now().uptimeNanoseconds + 2_000_000_000
        while queue.operationCount > 0 && DispatchTime.now().uptimeNanoseconds < deadline { Thread.sleep(forTimeInterval: 0.05) }
        queue.cancelAllOperations()
    }
}
func reportDeveloper(_ app: App, module: String, context: ErrorContext, error: Error, metrics: Metrics) throws {
    let sender = try app.sender(object(app.config.values["telegram"])["dev_chat"] ?? null, metrics: metrics)
    let channel = context.channel ?? sender.channel
    let filter: Doc; let linkTitle: String
    if let link = context.link {
        filter = ["channel": channel.lowercased(), "url": link.lowercased()]; linkTitle = "link: \(link)\n"
    } else {
        let formatter = DateFormatter(); formatter.dateFormat = "yyyy-MM-dd"
        filter = ["channel": channel.lowercased(), "link": "_NO_", "date": formatter.string(from: Date())]; linkTitle = ""
    }
    guard let record = try app.db.claim("errors", filter, ["$inc": ["cnt": 1], "$set": ["ts": dateBSON()]],
        projection: ["cnt": 1, "_id": 0], upsert: true), record["cnt"] is NSNumber else { throw R2TError.database(-1) }
    let title = "submodule: \(module)\nchannel: \(channel)\n\(linkTitle)error_cnt: \(Int(number(record["cnt"])))"
    try sender.sendText("<b>r2t error</b>\n\(title)\n\n\n<pre>\(safeError(error))</pre>", parse: "HTML")
}
